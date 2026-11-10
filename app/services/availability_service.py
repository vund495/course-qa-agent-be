"""Teacher availability for one calendar day (AI-158 Phase 2).

The day status is intentionally small: ``present`` is the implicit default and
``off`` removes a trainer from auto-handover candidates. Planned leave is
stored separately in ``leave_request``; when a leave request is accepted, the
leave service writes ``off`` rows here for every covered day.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.attendance import TRAINER_DAY_STATUSES, TrainerDayStatus
from app.models.course import Class, ClassTrainer
from app.models.user import User
from app.services.course_service import DomainError

DEFAULT_DAY_STATUS = "present"


def get_day_status(db: Session, trainer_id: uuid.UUID, day: date) -> str:
    """Return ``present`` / ``off`` for a trainer on ``day``.

    Missing rows mean the trainer has not marked anything, which is treated as
    available (``present``).
    """
    status = (
        db.query(TrainerDayStatus.status)
        .filter(
            TrainerDayStatus.trainer_id == trainer_id,
            TrainerDayStatus.date == day,
        )
        .scalar()
    )
    return status or DEFAULT_DAY_STATUS


def set_day_status(
    db: Session,
    trainer_id: uuid.UUID,
    day: date,
    status: str,
    recorded_by: uuid.UUID,
    note: str | None = None,
) -> TrainerDayStatus:
    """Create or update the ``(trainer_id, day)`` day-status row.

    The unique constraint on ``(trainer_id, date)`` is the source of truth. A
    concurrent insert is retried once after rollback so the second writer
    updates the winning row instead of failing the request. Marking ``off``
    sweeps open tickets; marking ``present`` clears this trainer's admin queue.
    """
    if status not in TRAINER_DAY_STATUSES:
        raise DomainError(f"Status must be one of: {', '.join(TRAINER_DAY_STATUSES)}.")

    row = (
        db.query(TrainerDayStatus)
        .filter(
            TrainerDayStatus.trainer_id == trainer_id,
            TrainerDayStatus.date == day,
        )
        .first()
    )

    if row is None:
        row = TrainerDayStatus(
            trainer_id=trainer_id,
            date=day,
            status=status,
            note=note,
            recorded_by=recorded_by,
        )
        db.add(row)
    else:
        row.status = status
        row.note = note
        row.recorded_by = recorded_by

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = (
            db.query(TrainerDayStatus)
            .filter(
                TrainerDayStatus.trainer_id == trainer_id,
                TrainerDayStatus.date == day,
            )
            .one()
        )
        row.status = status
        row.note = note
        row.recorded_by = recorded_by
        db.commit()

    db.refresh(row)

    # Imported lazily because handover_service depends on available_trainers()
    # in this module; a module-level import would create a cycle.
    from app.services.handover_service import clear_queue_for, sweep_for_trainer

    if status == "off":
        sweep_for_trainer(db, trainer_id, day)
    else:
        clear_queue_for(db, trainer_id, day)

    return row


def is_available(db: Session, trainer_id: uuid.UUID, day: date) -> bool:
    """Return whether a trainer is available for handover on ``day``."""
    return get_day_status(db, trainer_id, day) != "off"


def available_trainers(
    db: Session,
    class_id: uuid.UUID,
    day: date,
) -> list[User]:
    """Return primary + co-trainers of a class who are not marked ``off``.

    Primary trainer comes first, then co-trainers in assignment order. Users
    are de-duplicated in case a co-trainer link duplicates the primary slot.
    """
    clazz = db.query(Class).filter(Class.id == class_id).first()
    if clazz is None:
        raise DomainError("Class does not exist.")

    users: dict[uuid.UUID, User] = {}

    primary = db.query(User).filter(User.id == clazz.trainer_id).first()
    if primary is not None:
        users[primary.id] = primary

    co_trainers = (
        db.query(User)
        .join(ClassTrainer, ClassTrainer.trainer_id == User.id)
        .filter(ClassTrainer.class_id == clazz.id)
        .order_by(ClassTrainer.created_at.asc(), User.full_name.asc())
        .all()
    )
    for trainer in co_trainers:
        users.setdefault(trainer.id, trainer)

    if not users:
        return []

    off_ids = {
        row[0]
        for row in db.query(TrainerDayStatus.trainer_id)
        .filter(
            TrainerDayStatus.date == day,
            TrainerDayStatus.status == "off",
            TrainerDayStatus.trainer_id.in_(list(users)),
        )
        .all()
    }
    return [trainer for trainer in users.values() if trainer.id not in off_ids]
