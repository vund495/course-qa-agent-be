"""Request schemas for the class-scoped chat API (AI-61)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.history import ChatCitation


class ChatRequest(BaseModel):
    """One question scoped to a specific class and optional conversation."""

    message: str
    class_id: uuid.UUID
    session_id: uuid.UUID | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message must not be empty.")
        return cleaned


class ChatQuotaResponse(BaseModel):
    """Daily allowance for the authenticated student (``limit=None`` = unlimited)."""

    limit: int | None
    used: int
    remaining: int | None
    resets_at: datetime | None


ConsentScopeKind = Literal["missing", "full"]


class WebConsentOfferRead(BaseModel):
    """Server-owned pending web-search consent offer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    scope_kind: ConsentScopeKind
    question: str
    query_scope: list[str]
    conflict_note: str | None = None
    conflict_citations: list[ChatCitation] = Field(default_factory=list)
    expires_at: datetime
    assistant_message_id: uuid.UUID | None = None


class WebConsentPendingResponse(BaseModel):
    """Pending offer for one owned class conversation, if it has not expired."""

    offer: WebConsentOfferRead | None = None


class WebConsentDecisionRequest(BaseModel):
    """Explicit consent action bound to the current class conversation."""

    decision: Literal["accept", "decline"]
    class_id: uuid.UUID
    session_id: uuid.UUID


class WebConsentResult(BaseModel):
    """Outcome of an explicit consent action.

    A consumed offer always returns its existing web answer on a duplicate
    click; it never starts a second search.
    """

    offer_id: uuid.UUID
    status: Literal["accepted", "declined", "already_consumed"]
    answer: str | None = None
    citations: list[ChatCitation] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    assistant_message_id: uuid.UUID | None = None
