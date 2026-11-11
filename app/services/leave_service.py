"""Planned leave requests and their effect on ticket ownership (AI-158 Phase 5).

A leave request is intentionally small: trainer A asks trainer B to cover a
date range. Accepting the request marks A ``off`` for every day in the range;
the day-status sweep then reuses the accepted request to prefer B as the manual
handover target.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.attendance import LeaveRequest
from app.models.user import User
from app.services import availability_service
from app.services.course_service import DomainError, class_ids_for_trainer
from app.services.holiday_service import local_date
from app.services.user_service import role_name_of


class LeaveConflictError(DomainError):
    """Raised when a leave request has already been answered."""


def _shared_class(
    db: Session, trainer_id: uuid.UUID, target_trainer_id: uuid.UUID
) -> bool:
    trainer_classes = class_ids_for_trainer(db, trainer_id, active_only=True)
    target_classes = class_ids_for_trainer(db, target_trainer_id, active_only=True)
    return bool(trainer_classes & target_classes)


def create_leave(
    db: Session,
    *,
    trainer_id: uuid.UUID,
    date_from: date,
    date_to: date,
    target_trainer_id: uuid.UUID,
    reason: str | None = None,
) -> LeaveRequest:
    """Create a pending leave request for a trainer's colleague."""
    if date_from > date_to:
        raise DomainError("date_from must be on or before date_to.")
    if trainer_id == target_trainer_id:
        raise DomainError("You cannot delegate to yourself.")

    target = db.query(User).filter(User.id == target_trainer_id).first()
    if (
        target is None
        or (role_name_of(target) or "").upper() != "TRAINER"
        or not _shared_class(db, trainer_id, target.id)
    ):
        raise DomainError("Target trainer does not teach this class.")

    leave = LeaveRequest(
        trainer_id=trainer_id,
        date_from=date_from,
        date_to=date_to,
        target_trainer_id=target_trainer_id,
        reason=reason,
        status="pending",
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    return leave


def list_my_leaves(db: Session, *, trainer_id: uuid.UUID) -> list[LeaveRequest]:
    """Return requests the trainer sent or received, newest first."""
    return (
        db.query(LeaveRequest)
        .filter(
            (LeaveRequest.trainer_id == trainer_id)
            | (LeaveRequest.target_trainer_id == trainer_id)
        )
        .order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
        .all()
    )


def _each_day(date_from: date, date_to: date) -> list[date]:
    days: list[date] = []
    cursor = date_from
    while cursor <= date_to:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def respond_leave(
    db: Session,
    *,
    leave_id: uuid.UUID,
    actor_id: uuid.UUID,
    accept: bool,
) -> LeaveRequest | None:
    """Accept or reject a pending leave request as the chosen target trainer.

    Accepting marks the requester ``off`` for every covered day. The leave row is
    committed as ``accepted`` first so ``pick_replacement`` can prefer the target
    while it sweeps each day.
    """
    leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()
    if leave is None:
        return None
    if leave.target_trainer_id != actor_id:
        raise PermissionError("This leave request is not assigned to you.")
    if leave.status != "pending":
        raise LeaveConflictError("This leave request was already answered.")

    now = datetime.now(UTC)
    leave.status = "accepted" if accept else "rejected"
    leave.responded_by = actor_id
    leave.responded_at = now
    db.commit()
    db.refresh(leave)

    if accept:
        for day in _each_day(leave.date_from, leave.date_to):
            availability_service.set_day_status(
                db,
                leave.trainer_id,
                day,
                "off",
                actor_id,
                note="Accepted leave request.",
            )
    else:
        # Rejected coverage falls back to the normal least-open auto flow. The
        # rejected target is excluded so the same trainer is not picked again.
        from app.services.handover_service import sweep_for_trainer

        sweep_for_trainer(
            db,
            leave.trainer_id,
            local_date(datetime.now(UTC)),
            exclude_ids={leave.target_trainer_id},
        )

    db.refresh(leave)
    return leave
