"""Yearly holiday calendar management and class member access."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.models.attendance import Holiday
from app.models.course import Class
from app.models.user import User
from app.routers.attendance.permissions import require_class_member_or_staff
from app.schemas.holiday import HolidayRead, HolidayWrite
from app.services.holiday_service import holidays_between

router = APIRouter(tags=["holidays"])


@router.get("/admin/holidays", response_model=list[HolidayRead])
def list_admin_holidays(
    year: int = Query(ge=1, le=9999),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """List system and class holidays within one calendar year."""
    return (
        db.query(Holiday)
        .filter(Holiday.date >= date(year, 1, 1), Holiday.date <= date(year, 12, 31))
        .order_by(Holiday.date, Holiday.scope, Holiday.name)
        .all()
    )


@router.get("/classes/{class_id}/holidays", response_model=list[HolidayRead])
def list_class_holidays(
    class_id: uuid.UUID,
    year: int = Query(ge=1, le=9999),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List the system and class holidays applicable to a class member."""
    require_class_member_or_staff(db, user, class_id)
    return holidays_between(db, date(year, 1, 1), date(year, 12, 31), class_id)


def _save_holiday(db: Session, row: Holiday, payload: HolidayWrite) -> Holiday:
    if payload.class_id is not None and db.get(Class, payload.class_id) is None:
        raise HTTPException(status_code=404, detail="Class not found.")
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="A holiday already exists for this date and scope."
        ) from exc
    db.refresh(row)
    return row


@router.post("/admin/holidays", response_model=HolidayRead, status_code=201)
def create_holiday(
    payload: HolidayWrite,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Create a system or class holiday."""
    return _save_holiday(db, Holiday(), payload)


@router.put("/admin/holidays/{holiday_id}", response_model=HolidayRead)
def update_holiday(
    holiday_id: uuid.UUID,
    payload: HolidayWrite,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Replace an existing holiday definition."""
    row = db.get(Holiday, holiday_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Holiday not found.")
    return _save_holiday(db, row, payload)


@router.delete("/admin/holidays/{holiday_id}", status_code=204)
def delete_holiday(
    holiday_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Delete a holiday without changing persisted sessions."""
    row = db.get(Holiday, holiday_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Holiday not found.")
    db.delete(row)
    db.commit()
    return Response(status_code=204)
