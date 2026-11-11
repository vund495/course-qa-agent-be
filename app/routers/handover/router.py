"""Trainer day-status endpoints (AI-158 Phase 2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.attendance import TrainerDayStatus
from app.models.user import User
from app.routers.attendance.permissions import require_class_staff
from app.schemas.handover import (
    AdminQueueItem,
    HandoverRead,
    LeaveRequestCreate,
    LeaveRequestRead,
    TrainerDayStatusRead,
    TrainerDayStatusSet,
)
from app.services import (
    availability_service,
    course_service,
    handover_service,
    leave_service,
    ticket_service,
    user_service,
)
from app.services.course_service import DomainError
from app.services.holiday_service import VIETNAM_TZ, local_date
from app.services.leave_service import LeaveConflictError

router = APIRouter(prefix="/api", tags=["handover"])


def _today() -> date:
    return local_date(datetime.now(VIETNAM_TZ))


def _role_name(user: User) -> str:
    return (user_service.role_name_of(user) or "").upper()


def _require_trainer_or_admin(user: User) -> None:
    if _role_name(user) not in ("TRAINER", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trainer or admin only.",
        )


def _require_trainer(user: User) -> None:
    if _role_name(user) != "TRAINER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only trainers can do this.",
        )


def _require_admin(user: User) -> None:
    if _role_name(user) != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view the admin queue.",
        )


def _validate_manual_day_window(day: date) -> None:
    """Manual status changes are limited to today and the previous seven days."""
    today = _today()
    if day > today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date cannot be in the future.",
        )
    if day < today - timedelta(days=7):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only the last 7 days can be marked.",
        )


def _get_status_row(
    db: Session,
    trainer_id: uuid.UUID,
    day: date,
) -> TrainerDayStatus | None:
    return (
        db.query(TrainerDayStatus)
        .filter(
            TrainerDayStatus.trainer_id == trainer_id,
            TrainerDayStatus.date == day,
        )
        .first()
    )


def _build_read(
    trainer_id: uuid.UUID,
    trainer_name: str,
    day: date,
    row: TrainerDayStatus | None,
) -> TrainerDayStatusRead:
    return TrainerDayStatusRead(
        trainer_id=trainer_id,
        trainer_name=trainer_name,
        date=day,
        status=row.status if row is not None else availability_service.DEFAULT_DAY_STATUS,
        note=row.note if row is not None else None,
        recorded_by=row.recorded_by if row is not None else None,
        updated_at=row.updated_at if row is not None else None,
    )


@router.get(
    "/trainer-status",
    response_model=TrainerDayStatusRead,
    summary="Get my trainer day status",
)
def get_my_trainer_status(
    day: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainerDayStatusRead:
    """Return the caller's status for a day, defaulting to ``present``."""
    _require_trainer_or_admin(current_user)
    resolved_day = day or _today()
    row = _get_status_row(db, current_user.id, resolved_day)
    return _build_read(current_user.id, current_user.full_name, resolved_day, row)


@router.put(
    "/trainer-status",
    response_model=TrainerDayStatusRead,
    summary="Set a trainer day status",
)
def set_trainer_status(
    payload: TrainerDayStatusSet,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainerDayStatusRead:
    """Set ``present`` / ``off``. Admins may target another trainer via ``trainer_id``."""
    _require_trainer_or_admin(current_user)
    _validate_manual_day_window(payload.date)
    role = _role_name(current_user)
    target = current_user

    if payload.trainer_id is not None and payload.trainer_id != current_user.id:
        if role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change another trainer's status.",
            )
        target = db.query(User).filter(User.id == payload.trainer_id).first()
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trainer not found.",
            )

    row = availability_service.set_day_status(
        db,
        target.id,
        payload.date,
        payload.status,
        current_user.id,
        payload.note,
    )
    return _build_read(target.id, target.full_name, payload.date, row)


@router.get(
    "/classes/{class_id}/trainer-status",
    response_model=list[TrainerDayStatusRead],
    summary="List day status for all trainers of a class",
)
def list_class_trainer_status(
    class_id: uuid.UUID,
    day: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TrainerDayStatusRead]:
    """Return primary + co-trainer statuses; unmarked trainers default to ``present``."""
    try:
        clazz = require_class_staff(db, current_user, class_id)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only this class' teachers can view trainer status.",
            ) from exc
        raise

    resolved_day = day or _today()
    trainers = course_service.list_trainers(db, clazz.id)
    trainer_ids = [item["trainer_id"] for item in trainers]
    rows: list[TrainerDayStatus] = []
    if trainer_ids:
        rows = (
            db.query(TrainerDayStatus)
            .filter(
                TrainerDayStatus.trainer_id.in_(trainer_ids),
                TrainerDayStatus.date == resolved_day,
            )
            .all()
        )
    row_map = {row.trainer_id: row for row in rows}

    return [
        _build_read(
            item["trainer_id"],
            item["name"],
            resolved_day,
            row_map.get(item["trainer_id"]),
        )
        for item in trainers
    ]


@router.get(
    "/admin/tickets/queue",
    response_model=list[AdminQueueItem],
    summary="List tickets waiting for an administrator",
)
def list_admin_ticket_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AdminQueueItem]:
    _require_admin(current_user)
    return ticket_service.list_admin_queue(db)


@router.post(
    "/leave-requests",
    response_model=LeaveRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a planned leave request",
)
def create_leave_request(
    payload: LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeaveRequestRead:
    _require_trainer(current_user)
    try:
        leave = leave_service.create_leave(
            db,
            trainer_id=current_user.id,
            date_from=payload.date_from,
            date_to=payload.date_to,
            target_trainer_id=payload.target_trainer_id,
            reason=payload.reason,
        )
    except DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LeaveRequestRead.model_validate(leave)


@router.get(
    "/leave-requests/mine",
    response_model=list[LeaveRequestRead],
    summary="List my sent and incoming leave requests",
)
def list_my_leave_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LeaveRequestRead]:
    _require_trainer(current_user)
    return [
        LeaveRequestRead.model_validate(row)
        for row in leave_service.list_my_leaves(db, trainer_id=current_user.id)
    ]


@router.post(
    "/leave-requests/{leave_id}/accept",
    response_model=LeaveRequestRead,
    summary="Accept a leave request and transfer covered tickets",
)
def accept_leave_request(
    leave_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeaveRequestRead:
    _require_trainer(current_user)
    try:
        leave = leave_service.respond_leave(
            db, leave_id=leave_id, actor_id=current_user.id, accept=True
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LeaveConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if leave is None:
        raise HTTPException(status_code=404, detail="Leave request not found.")
    return LeaveRequestRead.model_validate(leave)


@router.post(
    "/leave-requests/{leave_id}/reject",
    response_model=LeaveRequestRead,
    summary="Reject a leave request and run the automatic sweep",
)
def reject_leave_request(
    leave_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeaveRequestRead:
    _require_trainer(current_user)
    try:
        leave = leave_service.respond_leave(
            db, leave_id=leave_id, actor_id=current_user.id, accept=False
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LeaveConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if leave is None:
        raise HTTPException(status_code=404, detail="Leave request not found.")
    return LeaveRequestRead.model_validate(leave)


@router.get(
    "/handovers/mine",
    response_model=list[HandoverRead],
    summary="List pending handovers assigned to me",
)
def list_my_handovers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[HandoverRead]:
    _require_trainer(current_user)
    return [
        HandoverRead.model_validate(row)
        for row in handover_service.pending_handovers_for(db, current_user.id)
    ]


@router.post(
    "/handovers/{handover_id}/accept",
    response_model=HandoverRead,
    summary="Accept a pending handover",
)
def accept_handover(
    handover_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HandoverRead:
    _require_trainer(current_user)
    try:
        handover = handover_service.accept_handover(
            db, handover_id, current_user.id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return HandoverRead.model_validate(handover)


@router.post(
    "/handovers/{handover_id}/reject",
    response_model=HandoverRead,
    summary="Reject a pending handover and run the automatic sweep",
)
def reject_handover(
    handover_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HandoverRead:
    _require_trainer(current_user)
    try:
        handover = handover_service.reject_handover(
            db, handover_id, current_user.id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return HandoverRead.model_validate(handover)
