"""Shared fixtures for AI-158 handover router tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.config import settings
from app.core.database import Base, get_session_local, reset_engine
from app.core.deps import get_db
from app.main import app
from app.models.attendance import Holiday
from app.models.course import Class, ClassTrainer, Enrollment
from app.models.user import Role, User
from app.services.holiday_service import local_date


def _clear_today_system_holiday(db: Session) -> None:
    """Keep handover router tests on a working day.

    The app lifespan seeds the system holiday calendar, so when the suite runs
    on a real holiday (e.g. 20/11) the leave/handover sweeps skip the day and
    the flow assertions below silently stop exercising the code under test.
    Holiday behaviour has dedicated coverage in ``tests/test_holiday_service.py``.
    """
    today = local_date(datetime.now(UTC))
    removed = (
        db.query(Holiday)
        .filter(Holiday.date == today, Holiday.scope == "system")
        .delete(synchronize_session=False)
    )
    if removed:
        db.commit()


@pytest.fixture()
def handover_db(monkeypatch) -> Generator[Session, None, None]:
    monkeypatch.setattr("app.services.reranker_service.warm_up", lambda: None)

    import app.core.database as dbmod

    reset_engine()
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    dbmod._engine = engine
    dbmod._SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    dbmod._db_url = "sqlite://"
    Base.metadata.create_all(bind=engine)

    db = get_session_local("sqlite://")()

    admin_role = Role(name="ADMIN")
    trainer_role = Role(name="TRAINER")
    student_role = Role(name="STUDENT")
    db.add_all([admin_role, trainer_role, student_role])
    db.flush()

    admin = User(
        full_name="Admin User",
        email="admin@handover-router.test",
        role_id=admin_role.id,
        status="ACTIVE",
    )
    primary = User(
        full_name="Primary Trainer",
        email="primary@handover-router.test",
        role_id=trainer_role.id,
        status="ACTIVE",
    )
    co_trainer = User(
        full_name="Co Trainer",
        email="co@handover-router.test",
        role_id=trainer_role.id,
        status="ACTIVE",
    )
    other_trainer = User(
        full_name="Other Trainer",
        email="other@handover-router.test",
        role_id=trainer_role.id,
        status="ACTIVE",
    )
    student = User(
        full_name="Student User",
        email="student@handover-router.test",
        role_id=student_role.id,
        status="ACTIVE",
    )
    db.add_all([admin, primary, co_trainer, other_trainer, student])
    db.flush()

    clazz = Class(
        code="AI158-ROUTER-02",
        name="AI-158 Router Class 2",
        trainer_id=primary.id,
        semester="HK1",
        academic_year="2026-2027",
        status="ACTIVE",
        credits=3,
    )
    db.add(clazz)
    db.flush()
    db.add(ClassTrainer(class_id=clazz.id, trainer_id=co_trainer.id))
    db.add(
        Enrollment(
            class_id=clazz.id,
            student_id=student.id,
            status="ACTIVE",
        )
    )
    db.commit()

    db.info.update(
        admin_id=admin.id,
        primary_id=primary.id,
        co_trainer_id=co_trainer.id,
        other_trainer_id=other_trainer.id,
        student_id=student.id,
        class_id=clazz.id,
    )
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
        reset_engine()


@pytest.fixture()
def handover_client(handover_db: Session) -> Generator[TestClient, None, None]:
    def _override_db():
        yield handover_db

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        _clear_today_system_holiday(handover_db)
        yield test_client
    app.dependency_overrides.clear()
