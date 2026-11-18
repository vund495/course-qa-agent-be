"""Unit tests for handover_service core ."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core.database import Base
from app.models.attendance import Holiday, TicketHandover, TrainerDayStatus
from app.models.course import Class, ClassTrainer, Enrollment
from app.models.ticket import Ticket, TicketReply
from app.models.user import Role, User
from app.services import availability_service, handover_service, ticket_service
from app.services.course_service import DomainError
from app.services.holiday_service import local_date

DAY = date(2026, 11, 11)


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


def _make_user(db: Session, email: str, full_name: str, role_name: str = "TRAINER") -> User:
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


def _make_class(
    db: Session,
    primary: User,
    code: str = "AI158-HANDOVER-01",
    co_trainers: tuple[User, ...] = (),
) -> Class:
    clazz = Class(
        code=code,
        name="AI-158 Handover Class",
        trainer_id=primary.id,
        semester="HK1",
        academic_year="2026-2027",
        status="ACTIVE",
        credits=3,
    )
    db.add(clazz)
    db.flush()
    for trainer in co_trainers:
        db.add(ClassTrainer(class_id=clazz.id, trainer_id=trainer.id))
    db.commit()
    db.refresh(clazz)
    return clazz


def _make_student(db: Session, email: str = "student@handover.test") -> User:
    return _make_user(db, email, "Student User", role_name="STUDENT")


def _enroll(db: Session, clazz: Class, student: User) -> None:
    db.add(Enrollment(class_id=clazz.id, student_id=student.id, status="ACTIVE"))
    db.commit()


def _make_ticket(
    db: Session,
    clazz: Class,
    student: User,
    owner: User,
    *,
    status: str = "OPEN",
    queued_for_admin_at: datetime | None = None,
    created_at: datetime | None = None,
) -> Ticket:
    ticket = Ticket(
        class_id=clazz.id,
        student_id=student.id,
        question="How does this work?",
        citations=[],
        status=status,
        owner_trainer_id=owner.id,
        queued_for_admin_at=queued_for_admin_at,
        created_at=created_at,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_open_ticket_count_counts_only_open_owned_tickets(db_session):
    primary = _make_user(db_session, "primary@count.test", "Primary")
    co = _make_user(db_session, "co@count.test", "Co")
    student = _make_student(db_session)
    clazz = _make_class(db_session, primary)

    _make_ticket(db_session, clazz, student, primary)
    _make_ticket(db_session, clazz, student, primary)
    _make_ticket(db_session, clazz, student, primary, status="ANSWERED")
    _make_ticket(db_session, clazz, student, co)

    assert handover_service.open_ticket_count(db_session, primary.id) == 2
    assert handover_service.open_ticket_count(db_session, co.id) == 1


def test_pick_replacement_excludes_off_and_excluded_and_picks_least_open(db_session):
    primary = _make_user(db_session, "primary@pick.test", "Primary")
    co_a = _make_user(db_session, "co-a@pick.test", "Co A")
    co_b = _make_user(db_session, "co-b@pick.test", "Co B")
    student = _make_student(db_session)
    clazz = _make_class(db_session, primary, co_trainers=(co_a, co_b))

    availability_service.set_day_status(db_session, co_b.id, DAY, "off", primary.id)
    picked = handover_service.pick_replacement(
        db_session, clazz.id, DAY, exclude_ids={primary.id}
    )
    assert picked is not None and picked.id == co_a.id

    availability_service.set_day_status(db_session, co_b.id, DAY, "present", primary.id)
    _make_ticket(db_session, clazz, student, co_a)
    _make_ticket(db_session, clazz, student, co_a)
    picked = handover_service.pick_replacement(
        db_session, clazz.id, DAY, exclude_ids={primary.id}
    )
    assert picked is not None and picked.id == co_b.id

    picked = handover_service.pick_replacement(
        db_session, clazz.id, DAY, exclude_ids={primary.id, co_a.id, co_b.id}
    )
    assert picked is None


def test_assign_moves_owner_closes_pending_and_logs_reply(db_session):
    primary = _make_user(db_session, "primary@assign.test", "Primary Trainer")
    co = _make_user(db_session, "co@assign.test", "Co Trainer")
    student = _make_student(db_session)
    clazz = _make_class(db_session, primary, co_trainers=(co,))
    ticket = _make_ticket(
        db_session,
        clazz,
        student,
        primary,
        queued_for_admin_at=datetime(2026, 11, 10, tzinfo=UTC),
    )
    old_pending = TicketHandover(
        ticket_id=ticket.id,
        from_trainer_id=primary.id,
        to_trainer_id=co.id,
        reason="auto_absent",
        status="pending",
    )
    db_session.add(old_pending)
    db_session.commit()

    handover = handover_service.assign(
        db_session,
        ticket,
        co,
        "manual_transfer",
        primary.id,
        status="accepted",
    )

    db_session.refresh(ticket)
    db_session.refresh(old_pending)
    assert handover.ticket_id == ticket.id
    assert handover.from_trainer_id == primary.id
    assert handover.to_trainer_id == co.id
    assert handover.reason == "manual_transfer"
    assert handover.status == "accepted"
    assert handover.responded_at is not None
    assert ticket.owner_trainer_id == co.id
    assert ticket.queued_for_admin_at is None
    assert old_pending.status == "rejected"
    assert old_pending.responded_at is not None

    replies = db_session.query(TicketReply).filter(TicketReply.ticket_id == ticket.id).all()
    assert len(replies) == 1
    assert replies[0].user_id == primary.id
    assert replies[0].message == (
        "Ticket transferred from Primary Trainer to Co Trainer (manual_transfer)."
    )


def test_assign_pending_replaces_existing_pending_handover(db_session):
    primary = _make_user(db_session, "primary@pending.test", "Primary")
    co = _make_user(db_session, "co@pending.test", "Co")
    student = _make_student(db_session)
    clazz = _make_class(db_session, primary, co_trainers=(co,))
    ticket = _make_ticket(db_session, clazz, student, primary)
    old_pending = TicketHandover(
        ticket_id=ticket.id,
        from_trainer_id=primary.id,
        to_trainer_id=co.id,
        reason="auto_absent",
        status="pending",
    )
    db_session.add(old_pending)
    db_session.commit()

    handover = handover_service.assign(
        db_session, ticket, co, "manual_transfer", primary.id, status="pending"
    )

    db_session.refresh(old_pending)
    assert old_pending.status == "rejected"
    assert old_pending.responded_at is not None
    assert handover.status == "pending"
    assert handover.responded_at is None
    pending_count = (
        db_session.query(TicketHandover)
        .filter(
            TicketHandover.ticket_id == ticket.id,
            TicketHandover.status == "pending",
        )
        .count()
    )
    assert pending_count == 1


def test_assign_rejects_same_owner_and_invalid_inputs(db_session):
    primary = _make_user(db_session, "primary@invalid.test", "Primary")
    co = _make_user(db_session, "co@invalid.test", "Co")
    student = _make_student(db_session)
    clazz = _make_class(db_session, primary, co_trainers=(co,))
    ticket = _make_ticket(db_session, clazz, student, co)

    with pytest.raises(DomainError, match="already belongs"):
        handover_service.assign(db_session, ticket, co, "auto_absent", primary.id)
    with pytest.raises(DomainError, match="Reason must be one of"):
        handover_service.assign(db_session, ticket, primary, "bogus", co.id)
    with pytest.raises(DomainError, match="Status must be one of"):
        handover_service.assign(
            db_session, ticket, primary, "auto_absent", co.id, status="bogus"
        )

    ticket.status = "RESOLVED"
    db_session.commit()
    with pytest.raises(DomainError, match="Only open or answered"):
        handover_service.assign(db_session, ticket, primary, "auto_absent", co.id)


def test_queue_for_admin_keeps_owner_and_is_idempotent(db_session):
    primary = _make_user(db_session, "primary@queue.test", "Primary")
    student = _make_student(db_session)
    clazz = _make_class(db_session, primary)
    ticket = _make_ticket(db_session, clazz, student, primary)
    first_now = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)

    handover_service.queue_for_admin(db_session, ticket, now=first_now)
    assert ticket.queued_for_admin_at == first_now
    assert ticket.owner_trainer_id == primary.id

    handover_service.queue_for_admin(
        db_session, ticket, now=datetime(2026, 11, 11, 4, 0, tzinfo=UTC)
    )
    assert ticket.queued_for_admin_at == first_now
    assert db_session.query(TicketHandover).count() == 0
    reply = db_session.query(TicketReply).one()
    assert reply.message == (
        "All trainers are off today; the ticket is waiting for an administrator."
    )


def test_sweep_for_trainer_assigns_open_tickets_to_available_colleague(db_session):
    primary = _make_user(db_session, "primary@sweep.test", "Primary")
    co = _make_user(db_session, "co@sweep.test", "Co")
    student = _make_student(db_session)
    clazz = _make_class(db_session, primary, co_trainers=(co,))
    first = _make_ticket(db_session, clazz, student, primary)
    second = _make_ticket(db_session, clazz, student, primary)

    handled = handover_service.sweep_for_trainer(db_session, primary.id, DAY)

    db_session.refresh(first)
    db_session.refresh(second)
    assert handled == 2
    assert first.owner_trainer_id == co.id
    assert second.owner_trainer_id == co.id
    assert handover_service.open_ticket_count(db_session, primary.id) == 0
    assert handover_service.open_ticket_count(db_session, co.id) == 2
    handovers = db_session.query(TicketHandover).all()
    assert len(handovers) == 2
    assert all(row.reason == "auto_absent" for row in handovers)
    assert all(row.status == "accepted" for row in handovers)
    assert all(row.from_trainer_id == primary.id for row in handovers)
    assert all(row.to_trainer_id == co.id for row in handovers)


def test_sweep_for_trainer_skips_system_holiday(db_session):
    primary = _make_user(db_session, "primary@holiday.test", "Primary")
    co = _make_user(db_session, "co@holiday.test", "Co")
    student = _make_student(db_session)
    clazz = _make_class(db_session, primary, co_trainers=(co,))
    ticket = _make_ticket(db_session, clazz, student, primary)
    db_session.add(
        Holiday(date=DAY, name="Public holiday", type="solar", scope="system")
    )
    db_session.commit()

    handled = handover_service.sweep_for_trainer(db_session, primary.id, DAY)

    db_session.refresh(ticket)
    assert handled == 0
    assert ticket.owner_trainer_id == primary.id
    assert ticket.queued_for_admin_at is None
    assert db_session.query(TicketHandover).count() == 0
    assert db_session.query(TicketReply).count() == 0


def test_sweep_for_trainer_skips_only_the_holiday_class(db_session):
    primary = _make_user(db_session, "primary@class-holiday.test", "Primary")
    co = _make_user(db_session, "co@class-holiday.test", "Co")
    student = _make_student(db_session)
    class_a = _make_class(
        db_session,
        primary,
        code="AI158-HOLIDAY-A",
        co_trainers=(co,),
    )
    class_b = _make_class(
        db_session,
        primary,
        code="AI158-HOLIDAY-B",
        co_trainers=(co,),
    )
    ticket_a = _make_ticket(db_session, class_a, student, primary)
    ticket_b = _make_ticket(db_session, class_b, student, primary)
    db_session.add(
        Holiday(
            date=DAY,
            name="Class day off",
            type="admin",
            scope="class",
            class_id=class_a.id,
        )
    )
    db_session.commit()

    handled = handover_service.sweep_for_trainer(db_session, primary.id, DAY)

    db_session.refresh(ticket_a)
    db_session.refresh(ticket_b)
    assert handled == 1
    assert ticket_a.owner_trainer_id == primary.id
    assert ticket_a.queued_for_admin_at is None
    assert ticket_b.owner_trainer_id == co.id
    handovers = db_session.query(TicketHandover).all()
    assert len(handovers) == 1
    assert handovers[0].ticket_id == ticket_b.id
    assert handovers[0].to_trainer_id == co.id


def test_sweep_for_trainer_queues_when_everyone_else_is_off(db_session):
    primary = _make_user(db_session, "primary@alloff.test", "Primary")
    co = _make_user(db_session, "co@alloff.test", "Co")
    student = _make_student(db_session)
    clazz = _make_class(db_session, primary, co_trainers=(co,))
    first = _make_ticket(db_session, clazz, student, primary)
    second = _make_ticket(db_session, clazz, student, primary)
    availability_service.set_day_status(db_session, co.id, DAY, "off", primary.id)

    handled = handover_service.sweep_for_trainer(db_session, primary.id, DAY)

    db_session.refresh(first)
    db_session.refresh(second)
    assert handled == 2
    assert first.owner_trainer_id == primary.id
    assert second.owner_trainer_id == primary.id
    assert first.queued_for_admin_at is not None
    assert second.queued_for_admin_at is not None
    assert db_session.query(TicketHandover).count() == 0
    assert db_session.query(TicketReply).count() == 2

    queued_at = first.queued_for_admin_at
    assert handover_service.sweep_for_trainer(db_session, primary.id, DAY) == 0
    db_session.refresh(first)
    assert first.queued_for_admin_at == queued_at


def test_clear_queue_for_only_clears_the_trainers_own_tickets(db_session):
    primary = _make_user(db_session, "primary@clear.test", "Primary")
    co = _make_user(db_session, "co@clear.test", "Co")
    student = _make_student(db_session)
    clazz = _make_class(db_session, primary, co_trainers=(co,))
    queued_at = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)
    primary_queued = _make_ticket(
        db_session, clazz, student, primary, queued_for_admin_at=queued_at
    )
    co_queued = _make_ticket(db_session, clazz, student, co, queued_for_admin_at=queued_at)
    primary_not_queued = _make_ticket(db_session, clazz, student, primary)

    cleared = handover_service.clear_queue_for(db_session, primary.id, DAY)

    db_session.refresh(primary_queued)
    db_session.refresh(co_queued)
    db_session.refresh(primary_not_queued)
    assert cleared == 1
    assert primary_queued.queued_for_admin_at is None
    assert co_queued.queued_for_admin_at == queued_at.replace(tzinfo=None)
    assert primary_not_queued.queued_for_admin_at is None
    assert handover_service.clear_queue_for(db_session, primary.id, DAY) == 0


def test_create_student_ticket_sets_primary_owner_when_available(db_session):
    primary = _make_user(db_session, "primary@create-present.test", "Primary")
    student = _make_student(db_session, "student@create-present.test")
    clazz = _make_class(db_session, primary, code="AI158-CREATE-01")
    _enroll(db_session, clazz, student)

    ticket = ticket_service.create_student_ticket(
        db_session,
        student=student,
        class_id=clazz.id,
        question="How does this work?",
    )

    assert ticket is not None
    assert ticket.owner_trainer_id == primary.id
    assert ticket.queued_for_admin_at is None
    assert db_session.query(TicketHandover).count() == 0


def test_create_student_ticket_sweeps_when_primary_is_off(db_session):
    primary = _make_user(db_session, "primary@create-sweep.test", "Primary")
    co = _make_user(db_session, "co@create-sweep.test", "Co")
    student = _make_student(db_session, "student@create-sweep.test")
    clazz = _make_class(
        db_session,
        primary,
        code="AI158-CREATE-02",
        co_trainers=(co,),
    )
    _enroll(db_session, clazz, student)
    today = local_date(datetime.now(UTC))
    availability_service.set_day_status(db_session, primary.id, today, "off", primary.id)

    ticket = ticket_service.create_student_ticket(
        db_session,
        student=student,
        class_id=clazz.id,
        question="I need help today.",
    )

    assert ticket is not None
    assert ticket.owner_trainer_id == co.id
    assert ticket.queued_for_admin_at is None
    handover = db_session.query(TicketHandover).one()
    assert handover.ticket_id == ticket.id
    assert handover.from_trainer_id == primary.id
    assert handover.to_trainer_id == co.id
    assert handover.reason == "auto_absent"
    assert db_session.query(TicketReply).count() == 1


def test_create_student_ticket_queues_when_everyone_is_off(db_session):
    primary = _make_user(db_session, "primary@create-queue.test", "Primary")
    student = _make_student(db_session, "student@create-queue.test")
    clazz = _make_class(db_session, primary, code="AI158-CREATE-03")
    _enroll(db_session, clazz, student)
    today = local_date(datetime.now(UTC))
    availability_service.set_day_status(db_session, primary.id, today, "off", primary.id)

    ticket = ticket_service.create_student_ticket(
        db_session,
        student=student,
        class_id=clazz.id,
        question="Is anyone available?",
    )

    assert ticket is not None
    assert ticket.owner_trainer_id == primary.id
    assert ticket.queued_for_admin_at is not None
    assert db_session.query(TicketHandover).count() == 0
    reply = db_session.query(TicketReply).one()
    assert reply.message == (
        "All trainers are off today; the ticket is waiting for an administrator."
    )


def test_list_trainer_tickets_sweeps_when_trainer_is_off(db_session):
    primary = _make_user(db_session, "primary@list-sweep.test", "Primary")
    co = _make_user(db_session, "co@list-sweep.test", "Co")
    student = _make_student(db_session, "student@list-sweep.test")
    clazz = _make_class(
        db_session,
        primary,
        code="AI158-LIST-01",
        co_trainers=(co,),
    )
    _enroll(db_session, clazz, student)
    ticket = _make_ticket(db_session, clazz, student, primary)
    today = local_date(datetime.now(UTC))
    db_session.add(
        TrainerDayStatus(
            trainer_id=primary.id,
            date=today,
            status="off",
            recorded_by=primary.id,
        )
    )
    db_session.commit()

    items, total = ticket_service.list_trainer_tickets(db_session, trainer_id=primary.id)

    db_session.refresh(ticket)
    # The sweep moves the ticket to the co-trainer, so it leaves the inbox of
    # the trainer who is off instead of staying visible to both.
    assert total == 0
    assert items == []
    assert ticket.owner_trainer_id == co.id
    handover = db_session.query(TicketHandover).one()
    assert handover.ticket_id == ticket.id
    assert handover.to_trainer_id == co.id

    co_items, co_total = ticket_service.list_trainer_tickets(db_session, trainer_id=co.id)
    assert co_total == 1
    assert [item.id for item in co_items] == [ticket.id]


def test_sweep_chooses_least_open_candidate(db_session):
    primary = _make_user(db_session, "primary@least-open.test", "Primary")
    co_a = _make_user(db_session, "co-a@least-open.test", "Co A")
    co_b = _make_user(db_session, "co-b@least-open.test", "Co B")
    student = _make_student(db_session, "student@least-open.test")
    clazz = _make_class(
        db_session,
        primary,
        code="AI158-LEAST-01",
        co_trainers=(co_a, co_b),
    )
    _make_ticket(db_session, clazz, student, co_a)
    ticket = _make_ticket(db_session, clazz, student, primary)

    handled = handover_service.sweep_for_trainer(db_session, primary.id, DAY)

    db_session.refresh(ticket)
    assert handled == 1
    assert ticket.owner_trainer_id == co_b.id
    assert handover_service.open_ticket_count(db_session, co_a.id) == 1
    assert handover_service.open_ticket_count(db_session, co_b.id) == 1


def test_trainer_returning_does_not_reclaim_transferred_tickets(db_session):
    primary = _make_user(db_session, "primary@no-reclaim.test", "Primary")
    co = _make_user(db_session, "co@no-reclaim.test", "Co")
    student = _make_student(db_session, "student@no-reclaim.test")
    clazz = _make_class(
        db_session,
        primary,
        code="AI158-NORECLAIM-01",
        co_trainers=(co,),
    )
    ticket = _make_ticket(db_session, clazz, student, primary)

    availability_service.set_day_status(db_session, primary.id, DAY, "off", primary.id)
    db_session.refresh(ticket)
    assert ticket.owner_trainer_id == co.id

    availability_service.set_day_status(db_session, primary.id, DAY, "present", primary.id)
    db_session.refresh(ticket)
    assert ticket.owner_trainer_id == co.id
    assert ticket.queued_for_admin_at is None
    assert db_session.query(TicketHandover).count() == 1


def test_sweep_is_idempotent_for_assigned_tickets(db_session):
    primary = _make_user(db_session, "primary@idempotent-assign.test", "Primary")
    co = _make_user(db_session, "co@idempotent-assign.test", "Co")
    student = _make_student(db_session, "student@idempotent-assign.test")
    clazz = _make_class(
        db_session,
        primary,
        code="AI158-IDEMPOTENT-01",
        co_trainers=(co,),
    )
    ticket = _make_ticket(db_session, clazz, student, primary)

    assert handover_service.sweep_for_trainer(db_session, primary.id, DAY) == 1
    assert handover_service.sweep_for_trainer(db_session, primary.id, DAY) == 0

    db_session.refresh(ticket)
    assert ticket.owner_trainer_id == co.id
    assert db_session.query(TicketHandover).count() == 1
    assert db_session.query(TicketReply).count() == 1


def test_assign_retries_once_after_integrity_error(db_session, monkeypatch):
    primary = _make_user(db_session, "primary@concurrency.test", "Primary")
    co = _make_user(db_session, "co@concurrency.test", "Co")
    student = _make_student(db_session, "student@concurrency.test")
    clazz = _make_class(
        db_session,
        primary,
        code="AI158-CONCURRENCY-01",
        co_trainers=(co,),
    )
    ticket = _make_ticket(db_session, clazz, student, primary)
    original_commit = db_session.commit
    calls = {"count": 0}

    def flaky_commit():
        calls["count"] += 1
        if calls["count"] == 1:
            raise IntegrityError("simulated", {}, Exception("unique pending"))
        original_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)

    handover = handover_service.assign(
        db_session, ticket, co, "auto_absent", primary.id
    )

    assert calls["count"] == 2
    assert handover.status == "accepted"
    db_session.refresh(ticket)
    assert ticket.owner_trainer_id == co.id
    assert db_session.query(TicketHandover).count() == 1
    assert db_session.query(TicketReply).count() == 1


def test_expire_open_tickets_skips_admin_queue(db_session):
    primary = _make_user(db_session, "primary@expire-queue.test", "Primary")
    student = _make_student(db_session, "student@expire-queue.test")
    clazz = _make_class(db_session, primary, code="AI158-EXPIRE-01")
    now = datetime.now(UTC)
    old = now - timedelta(days=8)
    queued = _make_ticket(
        db_session,
        clazz,
        student,
        primary,
        queued_for_admin_at=now,
        created_at=old,
    )
    normal = _make_ticket(db_session, clazz, student, primary, created_at=old)

    expired = ticket_service.expire_open_tickets(db_session, now=now)

    db_session.refresh(queued)
    db_session.refresh(normal)
    assert expired == 1
    assert queued.status == "OPEN"
    assert normal.status == "EXPIRED"


def test_escalate_stale_tickets_skips_admin_queue(db_session):
    primary = _make_user(db_session, "primary@escalate-queue.test", "Primary")
    co = _make_user(db_session, "co@escalate-queue.test", "Co")
    student = _make_student(db_session, "student@escalate-queue.test")
    clazz = _make_class(
        db_session,
        primary,
        code="AI158-ESCALATE-01",
        co_trainers=(co,),
    )
    now = datetime.now(UTC)
    old = now - timedelta(hours=25)
    queued = _make_ticket(
        db_session,
        clazz,
        student,
        primary,
        queued_for_admin_at=now,
        created_at=old,
    )
    normal = _make_ticket(db_session, clazz, student, primary, created_at=old)

    escalated = ticket_service.escalate_stale_tickets(
        db_session,
        now=now,
        class_ids={clazz.id},
    )

    db_session.refresh(queued)
    db_session.refresh(normal)
    assert escalated == 1
    assert queued.escalated_at is None
    assert queued.escalated_to_id is None
    assert normal.escalated_at is not None
    assert normal.escalated_to_id == co.id
