"""Unit tests for availability_service ."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core.database import Base
from app.models.attendance import TicketHandover, TrainerDayStatus
from app.models.course import Class, ClassTrainer
from app.models.ticket import Ticket, TicketReply
from app.models.user import Role, User
from app.services import availability_service
from app.services.course_service import DomainError

DAY = date(2026, 11, 10)


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


def _make_user(
    db: Session,
    email: str,
    full_name: str,
    role_name: str = "trainer",
) -> User:
    role = db.query(Role).filter(Role.name == role_name).first()
    if role is None:
        role = Role(name=role_name)
        db.add(role)
        db.flush()
    user = User(
        email=email,
        full_name=full_name,
        role_id=role.id,
        status="ACTIVE",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_class(db: Session, trainer: User, code: str = "AI158-01") -> Class:
    clazz = Class(
        code=code,
        name="AI-158 Availability",
        trainer_id=trainer.id,
        status="ACTIVE",
        semester="HK1",
        academic_year="2026-2027",
        credits=3,
    )
    db.add(clazz)
    db.commit()
    db.refresh(clazz)
    return clazz


def _add_co_trainer(db: Session, clazz: Class, trainer: User) -> None:
    db.add(ClassTrainer(class_id=clazz.id, trainer_id=trainer.id))
    db.commit()


def _make_student(db: Session, email: str = "student@example.com") -> User:
    return _make_user(db, email, "Student User", role_name="student")


def _make_ticket(
    db: Session,
    clazz: Class,
    student: User,
    owner: User,
    *,
    queued_for_admin_at: datetime | None = None,
) -> Ticket:
    ticket = Ticket(
        class_id=clazz.id,
        student_id=student.id,
        question="How does this work?",
        citations=[],
        owner_trainer_id=owner.id,
        queued_for_admin_at=queued_for_admin_at,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_get_day_status_defaults_to_present(db_session):
    trainer = _make_user(db_session, "default@example.com", "Default Trainer")

    assert availability_service.get_day_status(db_session, trainer.id, DAY) == "present"


def test_set_day_status_creates_then_updates_one_row(db_session):
    trainer = _make_user(db_session, "set@example.com", "Set Trainer")
    admin = _make_user(db_session, "admin@example.com", "Admin")

    created = availability_service.set_day_status(
        db_session,
        trainer.id,
        DAY,
        "off",
        admin.id,
        note="  sick  ",
    )

    assert created.status == "off"
    assert created.note == "  sick  "
    assert created.recorded_by == admin.id
    assert db_session.query(TrainerDayStatus).count() == 1

    updated = availability_service.set_day_status(
        db_session,
        trainer.id,
        DAY,
        "present",
        admin.id,
    )

    assert updated.id == created.id
    assert updated.status == "present"
    assert updated.note is None
    assert db_session.query(TrainerDayStatus).count() == 1
    assert availability_service.get_day_status(db_session, trainer.id, DAY) == "present"


def test_set_day_status_rejects_unknown_status(db_session):
    trainer = _make_user(db_session, "invalid@example.com", "Invalid Trainer")

    with pytest.raises(DomainError, match="Status must be one of"):
        availability_service.set_day_status(
            db_session,
            trainer.id,
            DAY,
            "vacation",
            trainer.id,
        )

    assert db_session.query(TrainerDayStatus).count() == 0


def test_is_available_follows_day_status(db_session):
    trainer = _make_user(db_session, "available@example.com", "Available Trainer")

    assert availability_service.is_available(db_session, trainer.id, DAY) is True

    availability_service.set_day_status(db_session, trainer.id, DAY, "off", trainer.id)
    assert availability_service.is_available(db_session, trainer.id, DAY) is False

    availability_service.set_day_status(db_session, trainer.id, DAY, "present", trainer.id)
    assert availability_service.is_available(db_session, trainer.id, DAY) is True


def test_available_trainers_returns_primary_and_co_trainers_not_off(db_session):
    primary = _make_user(db_session, "primary@example.com", "Primary Trainer")
    co_a = _make_user(db_session, "co-a@example.com", "Co A")
    co_b = _make_user(db_session, "co-b@example.com", "Co B")
    outsider = _make_user(db_session, "outsider@example.com", "Outsider")

    clazz = _make_class(db_session, primary)
    _add_co_trainer(db_session, clazz, co_a)
    _add_co_trainer(db_session, clazz, co_b)

    availability_service.set_day_status(db_session, co_b.id, DAY, "off", primary.id)
    availability_service.set_day_status(db_session, outsider.id, DAY, "off", primary.id)

    trainers = availability_service.available_trainers(db_session, clazz.id, DAY)

    assert [trainer.id for trainer in trainers] == [primary.id, co_a.id]


def test_available_trainers_returns_empty_when_everyone_is_off(db_session):
    primary = _make_user(db_session, "all-off@example.com", "All Off")
    clazz = _make_class(db_session, primary, code="AI158-02")

    availability_service.set_day_status(db_session, primary.id, DAY, "off", primary.id)

    assert availability_service.available_trainers(db_session, clazz.id, DAY) == []


def test_available_trainers_raises_when_class_missing(db_session):
    with pytest.raises(DomainError, match="Class does not exist"):
        availability_service.available_trainers(db_session, uuid.uuid4(), DAY)


def test_set_day_status_off_sweeps_open_tickets_to_available_colleague(db_session):
    primary = _make_user(db_session, "primary@status-sweep.test", "Primary")
    co = _make_user(db_session, "co@status-sweep.test", "Co")
    admin = _make_user(db_session, "admin@status-sweep.test", "Admin")
    student = _make_student(db_session, "student@status-sweep.test")
    clazz = _make_class(db_session, primary, code="AI158-03")
    _add_co_trainer(db_session, clazz, co)
    ticket = _make_ticket(db_session, clazz, student, primary)

    availability_service.set_day_status(db_session, primary.id, DAY, "off", admin.id)

    db_session.refresh(ticket)
    assert ticket.owner_trainer_id == co.id
    handover = db_session.query(TicketHandover).one()
    assert handover.from_trainer_id == primary.id
    assert handover.to_trainer_id == co.id
    assert handover.reason == "auto_absent"
    assert handover.status == "accepted"
    assert db_session.query(TicketReply).count() == 1


def test_set_day_status_off_queues_when_no_replacement_is_available(db_session):
    primary = _make_user(db_session, "primary@status-queue.test", "Primary")
    admin = _make_user(db_session, "admin@status-queue.test", "Admin")
    student = _make_student(db_session, "student@status-queue.test")
    clazz = _make_class(db_session, primary, code="AI158-04")
    ticket = _make_ticket(db_session, clazz, student, primary)

    availability_service.set_day_status(db_session, primary.id, DAY, "off", admin.id)

    db_session.refresh(ticket)
    assert ticket.owner_trainer_id == primary.id
    assert ticket.queued_for_admin_at is not None
    assert db_session.query(TicketHandover).count() == 0
    reply = db_session.query(TicketReply).one()
    assert reply.message == (
        "All trainers are off today; the ticket is waiting for an administrator."
    )


def test_set_day_status_present_clears_the_trainers_queue(db_session):
    primary = _make_user(db_session, "primary@status-present.test", "Primary")
    admin = _make_user(db_session, "admin@status-present.test", "Admin")
    student = _make_student(db_session, "student@status-present.test")
    clazz = _make_class(db_session, primary, code="AI158-05")
    ticket = _make_ticket(
        db_session,
        clazz,
        student,
        primary,
        queued_for_admin_at=datetime(2026, 11, 10, 3, 0, tzinfo=UTC),
    )

    availability_service.set_day_status(db_session, primary.id, DAY, "present", admin.id)

    db_session.refresh(ticket)
    assert ticket.queued_for_admin_at is None
