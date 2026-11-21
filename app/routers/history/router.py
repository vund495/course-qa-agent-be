"""History endpoints — Chat session and message history (/api/history)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.schemas.history import (
    ChatCitation,
    ChatDetailResponse,
    ChatMessageResponse,
    ChatSearchResponse,
    ChatSessionListResponse,
    ChatSessionResponse,
    DeleteSessionResponse,
    MessageCreateRequest,
    PendingWebConsent,
    SessionCreateRequest,
    SessionPinRequest,
    SessionRenameRequest,
)
from app.services import history_service, web_consent_service
from app.services.pagination import InvalidCursorError

router = APIRouter(prefix="/api/history", tags=["history"])

CursorSection = Literal["recent", "pinned"]


@router.get("", response_model=ChatSessionListResponse)
def list_sessions(
    class_id: uuid.UUID | None = Query(default=None, description="Optional class ID filter"),
    limit: int = Query(default=50, ge=1, le=100, description="Max items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset (legacy mode)"),
    section: CursorSection | None = Query(
        default=None,
        description=(
            "Cursor mode section: 'recent' (updated_at DESC) or 'pinned' (pinned_at ASC). "
            "Omit to use the legacy offset pagination."
        ),
    ),
    cursor: str | None = Query(
        default=None,
        description="Opaque keyset cursor returned as next_cursor by the previous page",
    ),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve chat sessions for the authenticated user (AC-04, AC-06, AI-185).

    Without ``section`` the legacy offset path runs unchanged. With ``section``
    the list is keyset-paginated and the response carries ``next_cursor``.
    """
    if section is None:
        if cursor is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cursor requires section.",
            )
        items, total = history_service.get_sessions_by_class(
            db=db,
            user_id=current_user.id,
            class_id=class_id,
            limit=limit,
            offset=offset,
        )
        return ChatSessionListResponse(items=items, total=total)

    try:
        items, total, next_cursor = history_service.get_sessions_cursor(
            db=db,
            user_id=current_user.id,
            section=section,
            cursor=cursor,
            class_id=class_id,
            limit=limit,
        )
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ChatSessionListResponse(items=items, total=total, next_cursor=next_cursor)


@router.get("/search", response_model=ChatSearchResponse)
def search_sessions_endpoint(
    q: str = Query(
        min_length=1,
        max_length=200,
        pattern=r"\S",
        description="Keyword to search in session titles and messages",
    ),
    class_id: uuid.UUID | None = Query(default=None, description="Optional class scope"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Search chat sessions by keyword (AC-01, AC-02, AI-101)."""
    query = q.strip()
    items, total = history_service.search_sessions(
        db=db,
        user_id=current_user.id,
        query=query,
        class_id=class_id,
        limit=limit,
        offset=offset,
    )
    return ChatSearchResponse(items=items, total=total, query=query)


@router.get("/{session_id}", response_model=ChatDetailResponse)
def get_session_detail(
    session_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve the full transcript of messages in chronological order (AC-05, AC-07)."""
    session = history_service.get_session_messages(
        db=db,
        session_id=session_id,
        user_id=current_user.id,
    )
    detail = ChatDetailResponse.model_validate(session)
    offer = web_consent_service.get_pending_offer(
        db,
        user_id=current_user.id,
        class_id=session.class_id,
        session_id=session.id,
    )
    if offer is not None:
        detail.pending_consent = PendingWebConsent(
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
    return detail


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Explicitly create a new chat session (AC-03)."""
    return history_service.create_session(
        db=db,
        user_id=current_user.id,
        class_id=payload.class_id,
        title=payload.title,
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def append_message(
    session_id: uuid.UUID,
    payload: MessageCreateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Append a single message to an existing session (AC-01, AC-02)."""
    # Verify ownership before appending
    history_service.get_session_messages(
        db=db,
        session_id=session_id,
        user_id=current_user.id,
    )
    return history_service.append_message(
        db=db,
        session_id=session_id,
        role=payload.role,
        content=payload.content,
        used_web_search=payload.used_web_search,
        citations=payload.citations,
        suggested_questions=payload.suggested_questions,
    )


@router.patch("/{session_id}", response_model=ChatSessionResponse)
def rename_session(
    session_id: uuid.UUID,
    payload: SessionRenameRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename one chat session owned by the authenticated user."""
    return history_service.rename_session(
        db=db,
        session_id=session_id,
        user_id=current_user.id,
        title=payload.title,
    )


@router.patch("/{session_id}/pin", response_model=ChatSessionResponse)
def toggle_pin_session(
    session_id: uuid.UUID,
    payload: SessionPinRequest | None = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pin or unpin one chat session owned by the authenticated user."""
    target_is_pinned = payload.is_pinned if payload else None
    return history_service.toggle_pin_session(
        db=db,
        session_id=session_id,
        user_id=current_user.id,
        is_pinned=target_is_pinned,
    )


@router.delete("/{session_id}", response_model=DeleteSessionResponse)
def delete_session(
    session_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a chat session and cascade cleanup (AC-05, AI-99)."""
    history_service.delete_session(
        db=db,
        session_id=session_id,
        user_id=current_user.id,
    )
    return DeleteSessionResponse()
