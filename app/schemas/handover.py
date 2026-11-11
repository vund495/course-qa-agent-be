"""Request and response schemas for teacher availability and handover (AI-158)."""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.tickets import TicketInboxItem

TrainerDayStatusValue = Literal["present", "off"]
HandoverReason = Literal["auto_absent", "manual_transfer"]
HandoverStatus = Literal["pending", "accepted", "rejected"]
LeaveRequestStatus = Literal["pending", "accepted", "rejected"]
_VIETNAM_TZ = timezone(timedelta(hours=7))


def _today() -> date_type:
    return datetime.now(_VIETNAM_TZ).date()


class TrainerDayStatusSet(BaseModel):
    """Payload for a trainer (self) or admin (any trainer) to set a day status."""

    trainer_id: uuid.UUID | None = None
    date: date_type = Field(default_factory=_today)
    status: TrainerDayStatusValue
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class TrainerDayStatusRead(BaseModel):
    """Current day status for one trainer. Defaults to ``present`` when unset."""

    model_config = ConfigDict(from_attributes=True)

    trainer_id: uuid.UUID
    trainer_name: str
    date: date_type
    status: TrainerDayStatusValue
    note: str | None = None
    recorded_by: uuid.UUID | None = None
    updated_at: datetime | None = None


class HandoverAssignRequest(BaseModel):
    to_trainer_id: uuid.UUID


class AdminQueueItem(TicketInboxItem):
    absent_trainers: list[str] = Field(default_factory=list)


class HandoverRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    ticket_question: str | None = None
    from_trainer_id: uuid.UUID
    from_trainer_name: str | None = None
    to_trainer_id: uuid.UUID
    to_trainer_name: str | None = None
    reason: HandoverReason
    status: HandoverStatus
    created_at: datetime
    responded_at: datetime | None = None


class LeaveRequestCreate(BaseModel):
    date_from: date_type
    date_to: date_type
    target_trainer_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_dates(self) -> LeaveRequestCreate:
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to.")
        return self

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class LeaveRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trainer_id: uuid.UUID
    trainer_name: str | None = None
    date_from: date_type
    date_to: date_type
    target_trainer_id: uuid.UUID
    target_trainer_name: str | None = None
    reason: str | None = None
    status: LeaveRequestStatus
    responded_by: uuid.UUID | None = None
    responded_at: datetime | None = None
    created_at: datetime
