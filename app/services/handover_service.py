"""Auto handover core for teacher absence (AI-158 Phase 3).

The service moves OPEN tickets away from an unavailable trainer. Holiday days
are ignored per class so a class-specific day off does not block other classes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.attendance import (
    HANDOVER_REASONS,
    HANDOVER_STATUSES,
    LeaveRequest,
    TicketHandover,
)
from app.models.course import Class, ClassTrainer
from app.models.ticket import Ticket, TicketReply
from app.models.user import User
from app.services.availability_service import available_trainers
from app.services.course_service import DomainError, class_ids_for_trainer, list_assistants
from app.services.holiday_service import HolidayBlocked, ensure_working_day, local_date

ASSIGNABLE_TICKET_STATUSES = ("OPEN", "ANSWERED")
TRANSFER_REPLY = "Ticket transferred from {from_name} to {to_name} ({reason})."
QUEUE_REPLY = "All trainers are off today; the ticket is waiting for an administrator."
REJECT_REPLY = "Handover from {from_name} was rejected; the ticket returns to the automatic queue."


class HandoverConflictError(DomainError):
    """Raised when a handover has already been answered."""


def open_ticket_count(db: Session, trainer_id: uuid.UUID) -> int:
    """Return the number of OPEN tickets currently owned by a trainer."""
    return (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.owner_trainer_id == trainer_id,
            Ticket.status == "OPEN",
        )
        .scalar()
        or 0
    )


def pick_replacement(
    db: Session,
    class_id: uuid.UUID,
    day: date,
    exclude_ids: set[uuid.UUID],
) -> User | None:
    """Pick an available trainer, preferring an accepted manual leave target.

    Manual coverage wins over load balancing (AC-05). When no accepted leave
    covers the day, the least-loaded trainer is chosen; ties fall back to the
    user id so the result is deterministic.
    """
    excluded = set(exclude_ids)
    # A chosen assistant takes priority only for this absent owner and class.
    preferred = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.status == "accepted",
            LeaveRequest.class_id == class_id,
            LeaveRequest.trainer_id.in_(excluded),
            LeaveRequest.date_from <= day,
            LeaveRequest.date_to >= day,
            LeaveRequest.target_trainer_id.isnot(None),
        )
        .order_by(LeaveRequest.created_at.desc())
        .first()
    )
    if preferred:
        from app.services.availability_service import is_available

        for assistant in list_assistants(db, class_id):
            if (
                assistant.id == preferred.target_trainer_id
                and assistant.id not in excluded
                and is_available(db, assistant.id, day)
            ):
                return assistant
    candidates = [
        trainer for trainer in available_trainers(db, class_id, day) if trainer.id not in excluded
    ]
    if not candidates:
        return None

    clazz = db.query(Class).filter(Class.id == class_id).first()
    if clazz is not None:
        class_trainer_ids = {clazz.trainer_id}
        class_trainer_ids.update(
            row[0]
            for row in db.query(ClassTrainer.trainer_id)
            .filter(ClassTrainer.class_id == class_id)
            .all()
        )
        candidate_ids = {trainer.id for trainer in candidates}
        preferred = (
            db.query(LeaveRequest)
            .filter(
                LeaveRequest.status == "accepted",
                LeaveRequest.date_from <= day,
                LeaveRequest.date_to >= day,
                LeaveRequest.trainer_id.in_(excluded),
                LeaveRequest.class_id.is_(None),
                LeaveRequest.target_trainer_id.in_(candidate_ids),
            )
            .order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
            .first()
        )
        if preferred is not None:
            for trainer in candidates:
                if trainer.id == preferred.target_trainer_id:
                    return trainer

    return min(
        candidates,
        key=lambda trainer: (open_ticket_count(db, trainer.id), str(trainer.id)),
    )


def _apply_assign(
    db: Session,
    ticket: Ticket,
    to: User,
    reason: str,
    actor_id: uuid.UUID,
    status: str,
    now: datetime,
) -> TicketHandover:
    from_id = ticket.owner_trainer_id or actor_id
    if from_id == to.id:
        raise DomainError("Ticket already belongs to this trainer.")

    from_user = db.query(User).filter(User.id == from_id).first()
    from_name = from_user.full_name if from_user is not None else "Unknown"

    pending = (
        db.query(TicketHandover)
        .filter(
            TicketHandover.ticket_id == ticket.id,
            TicketHandover.status == "pending",
        )
        .all()
    )
    for old in pending:
        old.status = "rejected"
        old.responded_at = now
    if pending:
        # Flush the updates before inserting a new pending row so the partial
        # unique index on (ticket_id) WHERE status='pending' is not violated.
        db.flush()

    handover = TicketHandover(
        ticket_id=ticket.id,
        from_trainer_id=from_id,
        to_trainer_id=to.id,
        reason=reason,
        status=status,
        responded_at=now if status != "pending" else None,
    )
    db.add(handover)
    if status == "accepted":
        ticket.owner_trainer_id = to.id
        ticket.queued_for_admin_at = None
        db.add(
            TicketReply(
                ticket_id=ticket.id,
                user_id=actor_id,
                message=TRANSFER_REPLY.format(
                    from_name=from_name,
                    to_name=to.full_name,
                    reason=reason,
                ),
            )
        )
    return handover


def assign(
    db: Session,
    ticket: Ticket,
    to: User,
    reason: str,
    actor_id: uuid.UUID,
    status: str = "accepted",
) -> TicketHandover:
    """Assign a ticket to ``to``, close old pending handovers, and log a reply."""
    if reason not in HANDOVER_REASONS:
        raise DomainError(f"Reason must be one of: {', '.join(HANDOVER_REASONS)}.")
    if status not in HANDOVER_STATUSES:
        raise DomainError(f"Status must be one of: {', '.join(HANDOVER_STATUSES)}.")
    if ticket.status not in ASSIGNABLE_TICKET_STATUSES:
        raise DomainError("Only open or answered tickets can be handed over.")
    if ticket.owner_trainer_id == to.id:
        raise DomainError("Ticket already belongs to this trainer.")

    now = datetime.now(UTC)
    expected_owner = ticket.owner_trainer_id
    for attempt in range(2):
        try:
            if status == "accepted":
                claimed = db.execute(
                    update(Ticket)
                    .where(
                        Ticket.id == ticket.id,
                        Ticket.owner_trainer_id == expected_owner,
                        Ticket.status.in_(ASSIGNABLE_TICKET_STATUSES),
                    )
                    .values(owner_trainer_id=to.id)
                    .execution_options(synchronize_session=False)
                )
                if not claimed.rowcount:
                    db.rollback()
                    raise HandoverConflictError(
                        "Ticket ownership changed; refresh before transferring."
                    )
            handover = _apply_assign(db, ticket, to, reason, actor_id, status, now)
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            db.refresh(ticket)
            if attempt or ticket.owner_trainer_id != expected_owner:
                raise HandoverConflictError(
                    "Ticket ownership changed; refresh before transferring."
                )

    db.refresh(handover)
    return handover


def queue_for_admin(
    db: Session,
    ticket: Ticket,
    now: datetime | None = None,
    actor_id: uuid.UUID | None = None,
) -> None:
    """Mark a ticket as waiting for an administrator, keeping its owner."""
    if ticket.queued_for_admin_at is not None:
        return
    queued_at = now or datetime.now(UTC)
    claimed = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket.id,
            Ticket.owner_trainer_id == ticket.owner_trainer_id,
            Ticket.queued_for_admin_at.is_(None),
            Ticket.status.in_(ASSIGNABLE_TICKET_STATUSES),
        )
        .values(queued_for_admin_at=queued_at)
        .execution_options(synchronize_session=False)
    )
    if not claimed.rowcount:
        db.rollback()
        return
    ticket.queued_for_admin_at = queued_at
    author_id = ticket.owner_trainer_id or actor_id
    if author_id is not None:
        db.add(
            TicketReply(
                ticket_id=ticket.id,
                user_id=author_id,
                message=QUEUE_REPLY,
            )
        )
    db.commit()


def sweep_for_trainer(
    db: Session,
    trainer_id: uuid.UUID,
    day: date,
    *,
    exclude_ids: set[uuid.UUID] | None = None,
) -> int:
    """Move / queue every OPEN ticket owned by a trainer on an absent day.

    Classes on a holiday are skipped without touching their tickets. Returns the
    number of tickets handled (assigned or queued). Tickets already queued are
    left untouched so repeated ``off`` requests stay idempotent. ``exclude_ids``
    is used by a rejected handover so the same recipient is not chosen again.
    """
    handled = 0
    extra_exclusions = set(exclude_ids or ())
    class_ids = sorted(
        class_ids_for_trainer(db, trainer_id, active_only=True),
        key=str,
    )
    for class_id in class_ids:
        try:
            ensure_working_day(db, day, class_id)
        except HolidayBlocked:
            continue
        tickets = (
            db.query(Ticket)
            .filter(
                Ticket.class_id == class_id,
                Ticket.owner_trainer_id == trainer_id,
                Ticket.status.in_(ASSIGNABLE_TICKET_STATUSES),
            )
            .order_by(Ticket.created_at.asc(), Ticket.id.asc())
            .all()
        )
        for ticket in tickets:
            replacement = pick_replacement(db, class_id, day, {trainer_id} | extra_exclusions)
            if replacement is None:
                if ticket.queued_for_admin_at is not None:
                    continue
                queue_for_admin(db, ticket, actor_id=trainer_id)
            else:
                try:
                    assign(db, ticket, replacement, "auto_absent", trainer_id, status="accepted")
                except HandoverConflictError:
                    continue
            handled += 1
    return handled


def clear_queue_for(
    db: Session,
    trainer_id: uuid.UUID,
    day: date,
) -> int:
    """Clear the admin queue for tickets still owned by a returning trainer."""
    del day  # Queue state is ticket-scoped; the day is kept for API symmetry.
    result = db.execute(
        update(Ticket)
        .where(
            Ticket.owner_trainer_id == trainer_id,
            Ticket.queued_for_admin_at.isnot(None),
        )
        .values(queued_for_admin_at=None)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    db.expire_all()
    return result.rowcount or 0


def pending_handovers_for(db: Session, trainer_id: uuid.UUID) -> list[TicketHandover]:
    """Return pending handovers addressed to a trainer, oldest first."""
    return (
        db.query(TicketHandover)
        .filter(
            TicketHandover.to_trainer_id == trainer_id,
            TicketHandover.status == "pending",
        )
        .order_by(TicketHandover.created_at.asc(), TicketHandover.id.asc())
        .all()
    )


def _pending_handover(db: Session, handover_id: uuid.UUID, actor_id: uuid.UUID) -> TicketHandover:
    handover = db.query(TicketHandover).filter(TicketHandover.id == handover_id).first()
    if handover is None:
        raise LookupError("Handover not found.")
    if handover.to_trainer_id != actor_id:
        raise PermissionError("This handover is not assigned to you.")
    if handover.status != "pending":
        raise HandoverConflictError("This handover was already answered.")
    return handover


def accept_handover(db: Session, handover_id: uuid.UUID, actor_id: uuid.UUID) -> TicketHandover:
    """Accept a pending handover and make the recipient the ticket owner."""
    handover = _pending_handover(db, handover_id, actor_id)
    ticket = handover.ticket
    now = datetime.now(UTC)
    handover.status = "accepted"
    handover.responded_at = now
    ticket.owner_trainer_id = handover.to_trainer_id
    ticket.queued_for_admin_at = None
    db.add(
        TicketReply(
            ticket_id=ticket.id,
            user_id=handover.from_trainer_id,
            message=TRANSFER_REPLY.format(
                from_name=handover.from_trainer_name or "Unknown",
                to_name=handover.to_trainer_name or "Unknown",
                reason=handover.reason,
            ),
        )
    )
    db.commit()
    db.refresh(handover)
    return handover


def reject_handover(db: Session, handover_id: uuid.UUID, actor_id: uuid.UUID) -> TicketHandover:
    """Reject a pending handover and immediately run the automatic sweep."""
    handover = _pending_handover(db, handover_id, actor_id)
    ticket = handover.ticket
    now = datetime.now(UTC)
    handover.status = "rejected"
    handover.responded_at = now
    db.add(
        TicketReply(
            ticket_id=ticket.id,
            user_id=handover.from_trainer_id,
            message=REJECT_REPLY.format(from_name=handover.from_trainer_name or "Unknown"),
        )
    )
    db.commit()
    db.refresh(handover)

    sweep_for_trainer(
        db,
        handover.from_trainer_id,
        local_date(now),
        exclude_ids={handover.to_trainer_id},
    )
    db.refresh(handover)
    return handover
