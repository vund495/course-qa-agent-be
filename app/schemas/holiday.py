"""Schemas for the admin and class holiday calendars."""

from __future__ import annotations

import uuid
from datetime import date as Date
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.attendance import HolidayScope, HolidayType


class HolidayWrite(BaseModel):
    """Complete holiday definition used for creation and replacement."""

    date: Date
    name: str = Field(min_length=1, max_length=200)
    type: HolidayType = "admin"
    scope: HolidayScope = "system"
    class_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Holiday name must not be blank.")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> HolidayWrite:
        if (self.scope == "class") != (self.class_id is not None):
            raise ValueError("Class scope requires class_id; system scope requires no class_id.")
        return self


class HolidayRead(HolidayWrite):
    """Persisted holiday definition."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
