"""User-bound web-search consent offers for the strict chat flow.

The server owns the offer scope. The client only chooses accept/decline; it
cannot supply or widen the web query. A consumed offer never starts a second
search, and an expired, declined, cross-user, or mismatched offer is rejected.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.chat import ChatWebConsent
from app.schemas.chat import WebConsentOfferRead
from app.schemas.history import ChatCitation
from app.services.strict_sources_service import StrictSourcesResult

CONSENT_TTL_SECONDS = 30 * 60

ConsentClaim = Literal["claimed", "already_consumed"]


def _now() -> datetime:
    return datetime.now(UTC)


def _query_scope_for_result(
    question: str,
    result: StrictSourcesResult,
) -> tuple[str, list[str]]:
    """Build the immutable web query scope from validated intent segments."""

    if result.status == "none":
        return "full", [question]

    segments: list[str] = []
    by_id = {intent.intent_id: intent for intent in result.intents}
    for intent_id in [*result.unsupported_intent_ids, *result.conflicting_intent_ids]:
        intent = by_id.get(intent_id)
        if intent is None:
            continue
        segment = (intent.question_segment or intent.question).strip()
        if segment and segment not in segments:
            segments.append(segment)
    if not segments:
        segments = [question]
    return "missing", segments


def expire_pending_offers(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> None:
    """Invalidate every old offer before a new turn for this conversation.

    This runs for every turn, not only turns that create a replacement offer,
    so a newer full or out-of-scope answer cannot leave an older offer usable.
    """

    db.execute(
        update(ChatWebConsent)
        .where(
            ChatWebConsent.user_id == user_id,
            ChatWebConsent.session_id == session_id,
            ChatWebConsent.status == "pending",
        )
        .values(status="expired")
        .execution_options(synchronize_session=False)
    )
    db.commit()


def create_offer_for_result(
    db: Session,
    *,
    user_id: uuid.UUID,
    class_id: uuid.UUID,
    session_id: uuid.UUID,
    assistant_message_id: uuid.UUID | None,
    question: str,
    result: StrictSourcesResult,
    conflict_note: str | None = None,
    conflict_citations: list[dict] | None = None,
) -> ChatWebConsent | None:
    """Create one pending offer for a partial/none course-evidence turn."""

    if result.status == "full":
        return None

    scope_kind, segments = _query_scope_for_result(question, result)
    query_text = " ".join(segments).strip()
    if not query_text:
        return None

    expire_pending_offers(db, user_id=user_id, session_id=session_id)
    offer = ChatWebConsent(
        user_id=user_id,
        class_id=class_id,
        session_id=session_id,
        assistant_message_id=assistant_message_id,
        scope_kind=scope_kind,
        question=question,
        query_text=query_text,
        scope_segments=segments,
        conflict_note=conflict_note,
        conflict_citations=conflict_citations or None,
        status="pending",
        expires_at=_now() + timedelta(seconds=CONSENT_TTL_SECONDS),
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


def offer_read(offer: ChatWebConsent) -> WebConsentOfferRead:
    return WebConsentOfferRead(
        id=offer.id,
        session_id=offer.session_id,
        scope_kind=offer.scope_kind,  # type: ignore[arg-type]
        question=offer.question,
        query_scope=list(offer.scope_segments or []),
        conflict_note=offer.conflict_note,
        conflict_citations=[
            ChatCitation.model_validate(citation)
            for citation in (offer.conflict_citations or [])
        ],
        expires_at=offer.expires_at,
        assistant_message_id=offer.assistant_message_id,
    )


def _load_owned_offer(
    db: Session,
    *,
    user_id: uuid.UUID,
    offer_id: uuid.UUID,
    class_id: uuid.UUID,
    session_id: uuid.UUID,
) -> ChatWebConsent:
    offer = db.get(ChatWebConsent, offer_id)
    if (
        offer is None
        or offer.user_id != user_id
        or offer.class_id != class_id
        or offer.session_id != session_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent offer not found.")
    return offer


def _expire_if_needed(db: Session, offer: ChatWebConsent) -> None:
    if offer.status == "pending" and offer.expires_at.replace(tzinfo=UTC) <= _now():
        offer.status = "expired"
        db.commit()


def get_pending_offer(
    db: Session,
    *,
    user_id: uuid.UUID,
    class_id: uuid.UUID,
    session_id: uuid.UUID,
) -> ChatWebConsent | None:
    """Return the newest unexpired pending offer for this exact conversation."""

    now = _now()
    db.execute(
        update(ChatWebConsent)
        .where(
            ChatWebConsent.user_id == user_id,
            ChatWebConsent.class_id == class_id,
            ChatWebConsent.session_id == session_id,
            ChatWebConsent.status == "pending",
            ChatWebConsent.expires_at <= now,
        )
        .values(status="expired")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return db.scalar(
        select(ChatWebConsent)
        .where(
            ChatWebConsent.user_id == user_id,
            ChatWebConsent.class_id == class_id,
            ChatWebConsent.session_id == session_id,
            ChatWebConsent.status == "pending",
            ChatWebConsent.expires_at > now,
        )
        .order_by(ChatWebConsent.created_at.desc())
        .limit(1)
    )


def decline_offer(
    db: Session,
    *,
    user_id: uuid.UUID,
    offer_id: uuid.UUID,
    class_id: uuid.UUID,
    session_id: uuid.UUID,
) -> ChatWebConsent:
    offer = _load_owned_offer(
        db,
        user_id=user_id,
        offer_id=offer_id,
        class_id=class_id,
        session_id=session_id,
    )
    _expire_if_needed(db, offer)
    if offer.status == "declined":
        return offer
    if offer.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consent offer is no longer pending.",
        )
    offer.status = "declined"
    offer.declined_at = _now()
    db.commit()
    db.refresh(offer)
    return offer


def claim_offer(
    db: Session,
    *,
    user_id: uuid.UUID,
    offer_id: uuid.UUID,
    class_id: uuid.UUID,
    session_id: uuid.UUID,
) -> tuple[ChatWebConsent, ConsentClaim]:
    """Atomically claim an offer for one search, or return its consumed answer.

    A duplicate click after completion returns ``already_consumed``. A
    concurrent click while the first search is in flight is rejected with 409,
    so two searches can never be started for the same offer.
    """

    offer = _load_owned_offer(
        db,
        user_id=user_id,
        offer_id=offer_id,
        class_id=class_id,
        session_id=session_id,
    )
    _expire_if_needed(db, offer)
    if offer.status == "consumed":
        if offer.web_message_id is not None:
            return offer, "already_consumed"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consent offer has already been consumed.",
        )
    if offer.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consent offer is no longer pending.",
        )

    result = db.execute(
        update(ChatWebConsent)
        .where(
            ChatWebConsent.id == offer.id,
            ChatWebConsent.user_id == user_id,
            ChatWebConsent.status == "pending",
        )
        .values(status="processing")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if result.rowcount != 1:
        db.refresh(offer)
        if offer.status == "consumed" and offer.web_message_id is not None:
            return offer, "already_consumed"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consent offer was already claimed.",
        )
    db.refresh(offer)
    return offer, "claimed"


def complete_offer(
    db: Session,
    *,
    offer: ChatWebConsent,
    web_message_id: uuid.UUID,
) -> ChatWebConsent:
    offer.status = "consumed"
    offer.web_message_id = web_message_id
    offer.consumed_at = _now()
    db.commit()
    db.refresh(offer)
    return offer


def release_offer(db: Session, *, offer: ChatWebConsent) -> None:
    """Allow one retry after a failed web search without another consent click."""

    if offer.status != "processing":
        return
    offer.status = "pending"
    db.commit()
