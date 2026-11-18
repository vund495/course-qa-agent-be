"""Admin-reviewed leave using AI-158 records and class-scoped optional coverage."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.attendance import LeaveRequest
from app.models.course import Enrollment
from app.models.user import User
from app.services.course_service import DomainError, class_ids_for_trainer
from app.services.holiday_service import local_date
from app.services.user_service import role_name_of


class LeaveConflictError(DomainError):
    """A leave decision cannot be applied or overlaps another request."""


def create_leave(
    db: Session,
    *,
    trainer_id: uuid.UUID,
    date_from: date,
    date_to: date,
    class_id: uuid.UUID,
    reason_type: str,
    reason_details: str | None = None,
    target_trainer_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> LeaveRequest:
    if date_from > date_to:
        raise DomainError("date_from must be on or before date_to.")
    if class_id not in class_ids_for_trainer(db, trainer_id, active_only=True):
        raise DomainError("You do not teach this class.")
    if target_trainer_id:
        target = db.get(User, target_trainer_id)
        assigned = (
            db.query(Enrollment)
            .filter_by(class_id=class_id, student_id=target_trainer_id, status="ACTIVE")
            .first()
        )
        if (
            not assigned
            or not target
            or target.status != "ACTIVE"
            or role_name_of(target) != "TEACHING_ASSISTANT"
        ):
            raise DomainError("Select an active assistant assigned to this class.")
    overlap = (
        db.query(LeaveRequest.id)
        .filter(
            LeaveRequest.trainer_id == trainer_id,
            LeaveRequest.class_id == class_id,
            LeaveRequest.status.in_(("pending", "accepted")),
            LeaveRequest.date_from <= date_to,
            LeaveRequest.date_to >= date_from,
        )
        .first()
    )
    if overlap:
        raise DomainError("A pending or approved leave already covers these dates for this class.")
    row = LeaveRequest(
        trainer_id=trainer_id,
        class_id=class_id,
        date_from=date_from,
        date_to=date_to,
        target_trainer_id=target_trainer_id,
        reason_type=reason_type,
        reason_details=reason_details,
        reason=reason_details or reason,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_my_leaves(db: Session, *, trainer_id: uuid.UUID) -> list[LeaveRequest]:
    return (
        db.query(LeaveRequest)
        .filter(LeaveRequest.trainer_id == trainer_id)
        .order_by(LeaveRequest.created_at.desc())
        .all()
    )


def respond_leave(
    db: Session,
    *,
    leave_id: uuid.UUID,
    actor_id: uuid.UUID,
    accept: bool,
    rejection_reason: str | None = None,
) -> LeaveRequest | None:
    actor = db.get(User, actor_id)
    if not actor or role_name_of(actor) != "ADMIN":
        raise PermissionError("Only admins can review leave requests.")
    leave = db.get(LeaveRequest, leave_id)
    if leave is None:
        return None
    target_status = "accepted" if accept else "rejected"
    current_status = leave.status
    if current_status == target_status:
        raise LeaveConflictError("This leave request already has that decision.")
    if accept:
        overlap = (
            db.query(LeaveRequest.id)
            .filter(
                LeaveRequest.id != leave.id,
                LeaveRequest.trainer_id == leave.trainer_id,
                LeaveRequest.class_id == leave.class_id,
                LeaveRequest.status.in_(("pending", "accepted")),
                LeaveRequest.date_from <= leave.date_to,
                LeaveRequest.date_to >= leave.date_from,
            )
            .first()
        )
        if overlap:
            raise LeaveConflictError(
                "Another pending or approved leave overlaps this date range."
            )
    result = db.execute(
        update(LeaveRequest)
        .where(LeaveRequest.id == leave_id, LeaveRequest.status == current_status)
        .values(
            status=target_status,
            responded_by=actor_id,
            responded_at=datetime.now(UTC),
            rejection_reason=None
            if accept
            else (rejection_reason or "").strip() or None,
        )
        .execution_options(synchronize_session=False)
    )
    if not result.rowcount:
        db.rollback()
        raise LeaveConflictError("This leave request changed; refresh and try again.")
    db.commit()
    db.refresh(leave)
    if accept:
        activate_approved_leaves(db)
    else:
        today = local_date(datetime.now(UTC))
        if leave.date_from <= today <= leave.date_to:
            from app.services.availability_service import is_available
            from app.services.handover_service import clear_queue_for

            if is_available(db, leave.trainer_id, today):
                clear_queue_for(db, leave.trainer_id, today)
    return leave


def activate_approved_leaves(db: Session, day: date | None = None) -> int:
    """Apply today's approved absences; never sweep tickets for future dates."""
    day = day or local_date(datetime.now(UTC))
    leaves = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.status == "accepted",
            LeaveRequest.date_from <= day,
            LeaveRequest.date_to >= day,
        )
        .all()
    )
    from app.services.handover_service import sweep_for_trainer

    handled = 0
    for trainer_id in {leave.trainer_id for leave in leaves}:
        handled += sweep_for_trainer(db, trainer_id, day)
    return handled
