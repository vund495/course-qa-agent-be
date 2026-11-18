"""AI-158: absence / handover schema and owner backfill.

Schema tests run on SQLite through ``create_all``. The backfill test runs the
real migration against a minimal pre-feature SQLite schema so the UPDATE and
downgrade paths are exercised, not just the ORM metadata.
"""

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (register tables)
from app.core.database import Base
from app.models.attendance import LeaveRequest, TrainerDayStatus


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _day_status(db_session, **overrides):
    row = TrainerDayStatus(
        **{
            "trainer_id": uuid.uuid4(),
            "date": date(2026, 11, 10),
            "status": "present",
            **overrides,
        }
    )
    db_session.add(row)
    db_session.flush()
    return row


def _leave_request(db_session, **overrides):
    row = LeaveRequest(
        **{
            "trainer_id": uuid.uuid4(),
            "date_from": date(2026, 11, 10),
            "date_to": date(2026, 11, 12),
            "target_trainer_id": uuid.uuid4(),
            **overrides,
        }
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_schema_creates_absence_tables_and_ticket_columns(db_session):
    inspector = inspect(db_session.get_bind())
    tables = set(inspector.get_table_names())

    assert {"trainer_day_status", "leave_request"} <= tables

    ticket_columns = {column["name"] for column in inspector.get_columns("ticket")}
    assert {"owner_trainer_id", "queued_for_admin_at"} <= ticket_columns


def test_trainer_day_status_rejects_unknown_status(db_session):
    with pytest.raises(IntegrityError):
        _day_status(db_session, status="vacation")
        db_session.commit()
    db_session.rollback()


def test_trainer_day_status_is_unique_per_trainer_and_date(db_session):
    trainer_id = uuid.uuid4()
    _day_status(db_session, trainer_id=trainer_id, status="present")
    db_session.commit()

    with pytest.raises(IntegrityError):
        _day_status(db_session, trainer_id=trainer_id, status="off")
        db_session.commit()
    db_session.rollback()


def test_leave_request_rejects_reversed_date_range(db_session):
    with pytest.raises(IntegrityError):
        _leave_request(
            db_session,
            date_from=date(2026, 11, 12),
            date_to=date(2026, 11, 10),
        )
        db_session.commit()
    db_session.rollback()


def test_leave_request_rejects_same_trainer_as_target(db_session):
    trainer_id = uuid.uuid4()

    with pytest.raises(IntegrityError):
        _leave_request(db_session, trainer_id=trainer_id, target_trainer_id=trainer_id)
        db_session.commit()
    db_session.rollback()


def test_leave_request_rejects_unknown_status(db_session):
    with pytest.raises(IntegrityError):
        _leave_request(db_session, status="cancelled")
        db_session.commit()
    db_session.rollback()


def test_leave_request_defaults_to_pending(db_session):
    leave = _leave_request(db_session)

    assert leave.status == "pending"


def _load_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0046_absence_handover.py"
    )
    spec = importlib.util.spec_from_file_location("absence_handover_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_backfills_ticket_owner_and_is_idempotent():
    migration = _load_migration()
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE "user" (id CHAR(32) PRIMARY KEY)')
        connection.exec_driver_sql(
            "CREATE TABLE class (id CHAR(32) PRIMARY KEY, trainer_id CHAR(32) NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE ticket ("
            "id CHAR(32) PRIMARY KEY, "
            "class_id CHAR(32) NOT NULL, "
            "student_id CHAR(32) NOT NULL, "
            "question TEXT NOT NULL, "
            "citations JSON NOT NULL, "
            "status VARCHAR(20) NOT NULL, "
            "created_at TIMESTAMP NOT NULL)"
        )

        class_id = uuid.uuid4().hex
        trainer_id = uuid.uuid4().hex
        ticket_id = uuid.uuid4().hex
        connection.execute(
            sa.text("INSERT INTO class (id, trainer_id) VALUES (:id, :trainer_id)"),
            {"id": class_id, "trainer_id": trainer_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO ticket"
                " (id, class_id, student_id, question, citations, status, created_at)"
                " VALUES (:id, :class_id, :student_id, :question, :citations, :status, :created_at)"
            ),
            {
                "id": ticket_id,
                "class_id": class_id,
                "student_id": uuid.uuid4().hex,
                "question": "How does this work?",
                "citations": "[]",
                "status": "OPEN",
                "created_at": "2026-11-10 00:00:00",
            },
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

        inspector = inspect(connection)
        assert {"trainer_day_status", "leave_request"} <= set(inspector.get_table_names())
        ticket_columns = {column["name"] for column in inspector.get_columns("ticket")}
        assert {"owner_trainer_id", "queued_for_admin_at"} <= ticket_columns
        owner = connection.scalar(
            sa.text("SELECT owner_trainer_id FROM ticket WHERE id = :id"),
            {"id": ticket_id},
        )
        assert owner == trainer_id

        # A second upgrade must not fail or overwrite the existing owner.
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert (
            connection.scalar(
                sa.text("SELECT owner_trainer_id FROM ticket WHERE id = :id"),
                {"id": ticket_id},
            )
            == trainer_id
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

        inspector = inspect(connection)
        assert "trainer_day_status" not in set(inspector.get_table_names())
        assert "leave_request" not in set(inspector.get_table_names())
        ticket_columns = {column["name"] for column in inspector.get_columns("ticket")}
        assert "owner_trainer_id" not in ticket_columns
        assert "queued_for_admin_at" not in ticket_columns

    engine.dispose()
