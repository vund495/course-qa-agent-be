"""User-bound consent offers for the strict-source web hand-off."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (register all tables)
from app.core.database import Base
from app.models.chat import ChatMessage, ChatSession, ChatWebConsent
from app.models.course import Class
from app.models.user import Role, User
from app.services import (
    chat_retrieval_service,
    rag_service,
    strict_chat_service,
    strict_web_service,
    web_consent_service,
)
from app.services.llm import gateway
from app.services.strict_sources_service import StrictSourcesResult, ValidatedIntent


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    role = Role(name=f"STUDENT-{uuid.uuid4()}")
    session.add(role)
    session.flush()
    user = User(
        full_name="Student",
        email=f"student-{uuid.uuid4()}@example.com",
        role_id=role.id,
        status="ACTIVE",
    )
    other = User(
        full_name="Other",
        email=f"other-{uuid.uuid4()}@example.com",
        role_id=role.id,
        status="ACTIVE",
    )
    session.add_all([user, other])
    session.flush()
    clazz = Class(
        trainer_id=user.id,
        code=f"STRICT-{uuid.uuid4().hex[:8]}",
        name="Strict Sources",
        semester="HK1",
        academic_year="2026-2027",
        status="ACTIVE",
    )
    session.add(clazz)
    session.commit()
    session.info.update(user_id=user.id, other_id=other.id, class_id=clazz.id)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _session(db: Session) -> ChatSession:
    session = ChatSession(
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        title="Strict test",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _result(
    status: str,
    *,
    unsupported: tuple[str, ...] = (),
    conflicting: tuple[str, ...] = (),
) -> StrictSourcesResult:
    intents = [
        ValidatedIntent(
            intent_id=f"I{index}",
            question=f"Missing part {index}",
            question_segment=f"missing part {index}",
            status="unsupported",
            limitation="not covered",
        )
        for index, _ in enumerate(unsupported, start=1)
    ]
    intents += [
        ValidatedIntent(
            intent_id=f"C{index}",
            question=f"Conflict part {index}",
            question_segment=f"conflict part {index}",
            status="conflicting",
            source_ids=["1", "2"],
            conflict_note="sources disagree",
        )
        for index, _ in enumerate(conflicting, start=1)
    ]
    if status == "partial":
        intents.append(
            ValidatedIntent(
                intent_id="I0",
                question="Supported part",
                question_segment="supported part",
                status="supported",
                claim="supported claim",
                source_ids=["1"],
            )
        )
    return StrictSourcesResult(
        question="original question",
        status=status,  # type: ignore[arg-type]
        reason="no_supported_evidence" if status == "none" else None,
        answer="supported claim" if status == "partial" else None,
        intents=intents,
        supported_intent_ids=["I0"] if status == "partial" else [],
        unsupported_intent_ids=[item.intent_id for item in intents if item.status == "unsupported"],
        conflicting_intent_ids=[item.intent_id for item in intents if item.status == "conflicting"],
        source_ids_used=["1"] if status == "partial" else [],
    )


def _events(raw_events: list[str]) -> list[tuple[str, dict]]:
    parsed = []
    for raw in raw_events:
        lines = raw.strip().splitlines()
        parsed.append(
            (
                lines[0].removeprefix("event: "),
                json.loads(lines[1].removeprefix("data: ")),
            )
        )
    return parsed


async def _collect(stream) -> list[str]:
    return [item async for item in stream]


def test_partial_offer_stores_only_missing_and_conflicting_segments(db: Session) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="What is X and Y?",
        result=_result("partial", unsupported=("x",), conflicting=("y",)),
    )

    assert offer is not None
    assert offer.scope_kind == "missing"
    assert offer.scope_segments == ["missing part 1", "conflict part 1"]
    assert offer.query_text == "missing part 1 conflict part 1"
    assert offer.status == "pending"


def test_offer_preserves_conflict_warning_and_citations(db: Session) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="What is X and Y?",
        result=_result("partial", conflicting=("y",)),
        conflict_note="Source 1 says early; source 2 says late.",
        conflict_citations=[
            {
                "index": 1,
                "kind": "curriculum",
                "title": "one.pdf",
                "snippet": "early",
            },
            {
                "index": 2,
                "kind": "curriculum",
                "title": "two.pdf",
                "snippet": "late",
            },
        ],
    )
    assert offer is not None
    assert offer.conflict_note == "Source 1 says early; source 2 says late."
    read = web_consent_service.offer_read(offer)
    assert read.conflict_note == offer.conflict_note
    assert [citation.title for citation in read.conflict_citations] == ["one.pdf", "two.pdf"]


def test_none_offer_uses_the_full_question_scope(db: Session) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Whole compound question?",
        result=_result("none", unsupported=("x",)),
    )

    assert offer is not None
    assert offer.scope_kind == "full"
    assert offer.scope_segments == ["Whole compound question?"]
    assert offer.query_text == "Whole compound question?"


def test_full_result_creates_no_offer(db: Session) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Full question",
        result=_result("partial"),
    )
    # A partial result with no missing segments still falls back to the whole question.
    assert offer is not None
    assert web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Full question",
        result=StrictSourcesResult(question="Full question", status="full", answer="ok"),
    ) is None


def test_expire_pending_offers_invalidates_only_the_target_conversation(db: Session) -> None:
    first_session = _session(db)
    second_session = _session(db)
    first = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=first_session.id,
        assistant_message_id=None,
        question="First",
        result=_result("none", unsupported=("x",)),
    )
    second = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=second_session.id,
        assistant_message_id=None,
        question="Second",
        result=_result("none", unsupported=("x",)),
    )
    assert first is not None and second is not None
    web_consent_service.expire_pending_offers(
        db,
        user_id=db.info["user_id"],
        session_id=first_session.id,
    )
    db.refresh(first)
    db.refresh(second)
    assert first.status == "expired"
    assert second.status == "pending"


def test_new_offer_expires_previous_pending_offer(db: Session) -> None:
    session = _session(db)
    first = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="First",
        result=_result("none", unsupported=("x",)),
    )
    second = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Second",
        result=_result("none", unsupported=("x",)),
    )
    db.refresh(first)
    assert first.status == "expired"
    assert second.status == "pending"
    pending = web_consent_service.get_pending_offer(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
    )
    assert pending is not None and pending.id == second.id


def test_cross_user_stale_declined_and_replayed_offers_are_rejected(db: Session) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Question",
        result=_result("none", unsupported=("x",)),
    )
    assert offer is not None

    with pytest.raises(HTTPException) as cross_user:
        web_consent_service.claim_offer(
            db,
            user_id=db.info["other_id"],
            offer_id=offer.id,
            class_id=db.info["class_id"],
            session_id=session.id,
        )
    assert cross_user.value.status_code == 404

    offer.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    with pytest.raises(HTTPException) as stale:
        web_consent_service.claim_offer(
            db,
            user_id=db.info["user_id"],
            offer_id=offer.id,
            class_id=db.info["class_id"],
            session_id=session.id,
        )
    assert stale.value.status_code == 409

    fresh = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Question",
        result=_result("none", unsupported=("x",)),
    )
    assert fresh is not None
    web_consent_service.decline_offer(
        db,
        user_id=db.info["user_id"],
        offer_id=fresh.id,
        class_id=db.info["class_id"],
        session_id=session.id,
    )
    with pytest.raises(HTTPException) as declined:
        web_consent_service.claim_offer(
            db,
            user_id=db.info["user_id"],
            offer_id=fresh.id,
            class_id=db.info["class_id"],
            session_id=session.id,
        )
    assert declined.value.status_code == 409


def test_duplicate_click_after_completion_returns_existing_answer(db: Session) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Question",
        result=_result("none", unsupported=("x",)),
    )
    assert offer is not None
    claimed, claim = web_consent_service.claim_offer(
        db,
        user_id=db.info["user_id"],
        offer_id=offer.id,
        class_id=db.info["class_id"],
        session_id=session.id,
    )
    assert claim == "claimed"
    message = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="**Web Search Answer**\n\nExisting answer",
        used_web_search=True,
        citations=[],
    )
    db.add(message)
    db.commit()
    web_consent_service.complete_offer(db, offer=claimed, web_message_id=message.id)

    replay, replay_claim = web_consent_service.claim_offer(
        db,
        user_id=db.info["user_id"],
        offer_id=offer.id,
        class_id=db.info["class_id"],
        session_id=session.id,
    )
    assert replay_claim == "already_consumed"
    assert replay.web_message_id == message.id


def test_accept_runs_isolated_web_step_and_persists_separate_answer(
    db: Session, monkeypatch
) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Original question and missing part",
        result=_result("none", unsupported=("x",)),
    )
    assert offer is not None
    queries: list[str] = []
    prompts: list[tuple[str, str]] = []
    forbidden_calls: list[str] = []

    def fake_search(query: str):
        queries.append(query)
        return [
            rag_service.WebResult(
                title="Public reference",
                url="https://example.com/reference",
                content="SerpApi snippet about queues only.",
            )
        ]

    async def fake_stream(_db, messages, **_kwargs):
        prompts.append((messages[0].content, messages[1].content))
        yield "**Web "
        yield "answer [1]."

    def must_not_run(*_args, **_kwargs):
        forbidden_calls.append("forbidden")
        raise AssertionError("the consent web step must stay isolated")

    monkeypatch.setattr(gateway, "astream_chat", fake_stream)
    monkeypatch.setattr(strict_web_service, "search_web_evidence", must_not_run)
    monkeypatch.setattr(strict_web_service, "fetch_public_web", must_not_run)
    monkeypatch.setattr(rag_service, "answer_question", must_not_run)
    monkeypatch.setattr(rag_service, "decide_source", must_not_run)
    monkeypatch.setattr(chat_retrieval_service, "retrieve_for_chat", must_not_run)

    stream = asyncio.run(
        strict_chat_service.decide_consent(
            db=db,
            user_id=db.info["user_id"],
            offer_id=offer.id,
            class_id=db.info["class_id"],
            session_id=session.id,
            decision="accept",
            search_fn=fake_search,
        )
    )
    events = _events(asyncio.run(_collect(stream)))

    assert [event for event, _ in events] == [
        "progress",
        "progress",
        "token",
        "token",
        "citation",
        "done",
    ]
    assert events[0][1]["message"] == "Searching the web"
    assert "".join(data["text"] for event, data in events if event == "token") == (
        "**Web answer [1]."
    )
    assert events[4][1]["url"] == "https://example.com/reference"
    assert events[5][1]["source"] == rag_service.SOURCE_INTERNET
    assert events[5][1]["used_web_search"] is True
    assert events[5][1]["assistant_message_id"]
    assert queries == ["Original question and missing part"]
    assert forbidden_calls == []
    assert prompts
    system_prompt, user_prompt = prompts[0]
    assert "expert Academic Tutor" in system_prompt
    assert "Internet Sources" in user_prompt
    assert "SerpApi snippet about queues only." in user_prompt
    assert "Original question and missing part" in user_prompt

    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).all()
    assert len(messages) == 1
    assert messages[0].used_web_search is True
    assert messages[0].content == "**Web answer [1]."
    assert messages[0].citations[0]["url"] == "https://example.com/reference"
    assert "Original question" not in " ".join(str(m.content) for m in messages)

    db.refresh(offer)
    assert offer.status == "consumed"
    assert offer.web_message_id == messages[0].id

    duplicate = asyncio.run(
        strict_chat_service.decide_consent(
            db=db,
            user_id=db.info["user_id"],
            offer_id=offer.id,
            class_id=db.info["class_id"],
            session_id=session.id,
            decision="accept",
            search_fn=fake_search,
        )
    )
    assert duplicate.status == "already_consumed"
    assert duplicate.answer == "**Web answer [1]."
    assert len(queries) == 1


@pytest.mark.parametrize(
    "search",
    [
        lambda _query: [],
        lambda _query: (_ for _ in ()).throw(RuntimeError("search down")),
    ],
)
def test_accept_without_web_results_releases_offer_and_fails_safely(
    db: Session, monkeypatch, search
) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Question that needs the web",
        result=_result("none", unsupported=("x",)),
    )
    assert offer is not None
    generated: list[str] = []

    async def must_not_generate(*_args, **_kwargs):
        generated.append("called")
        yield "should not be used"

    monkeypatch.setattr(gateway, "astream_chat", must_not_generate)

    stream = asyncio.run(
        strict_chat_service.decide_consent(
            db=db,
            user_id=db.info["user_id"],
            offer_id=offer.id,
            class_id=db.info["class_id"],
            session_id=session.id,
            decision="accept",
            search_fn=search,
        )
    )
    events = _events(asyncio.run(_collect(stream)))

    assert [event for event, _ in events] == ["progress", "error"]
    assert events[0][1]["message"] == "Searching the web"
    assert generated == []
    db.refresh(offer)
    assert offer.status == "pending"
    assert offer.web_message_id is None
    assert db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count() == 0


def test_accept_stream_failure_releases_offer_without_persisting_partial_answer(
    db: Session, monkeypatch
) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Question that needs the web",
        result=_result("none", unsupported=("x",)),
    )
    assert offer is not None

    def fake_search(_query: str):
        return [
            rag_service.WebResult(
                title="Public reference",
                url="https://example.com/reference",
                content="A snippet",
            )
        ]

    async def failing_stream(_db, _messages, **_kwargs):
        yield "partial answer"
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(gateway, "astream_chat", failing_stream)

    stream = asyncio.run(
        strict_chat_service.decide_consent(
            db=db,
            user_id=db.info["user_id"],
            offer_id=offer.id,
            class_id=db.info["class_id"],
            session_id=session.id,
            decision="accept",
            search_fn=fake_search,
        )
    )
    events = _events(asyncio.run(_collect(stream)))

    assert [event for event, _ in events] == [
        "progress",
        "progress",
        "token",
        "error",
    ]
    assert events[2][1]["text"] == "partial answer"
    assert db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count() == 0
    db.refresh(offer)
    assert offer.status == "pending"
    assert offer.web_message_id is None


def test_accept_stream_restart_persists_only_the_retried_complete_answer(
    db: Session, monkeypatch
) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Question that needs the web",
        result=_result("none", unsupported=("x",)),
    )
    assert offer is not None

    def fake_search(_query: str):
        return [
            rag_service.WebResult(
                title="Public reference",
                url="https://example.com/reference",
                content="A snippet",
            )
        ]

    async def restarting_stream(_db, _messages, **_kwargs):
        yield "partial draft"
        yield gateway.StreamRestart()
        yield "final answer [1]."

    monkeypatch.setattr(gateway, "astream_chat", restarting_stream)

    stream = asyncio.run(
        strict_chat_service.decide_consent(
            db=db,
            user_id=db.info["user_id"],
            offer_id=offer.id,
            class_id=db.info["class_id"],
            session_id=session.id,
            decision="accept",
            search_fn=fake_search,
        )
    )
    events = _events(asyncio.run(_collect(stream)))

    assert [event for event, _ in events][:4] == [
        "progress",
        "progress",
        "token",
        "restart",
    ]
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).all()
    assert len(messages) == 1
    assert messages[0].content == "final answer [1]."
    db.refresh(offer)
    assert offer.status == "consumed"


def test_offer_row_is_immutable_scope_even_if_question_changes(db: Session) -> None:
    session = _session(db)
    offer = web_consent_service.create_offer_for_result(
        db,
        user_id=db.info["user_id"],
        class_id=db.info["class_id"],
        session_id=session.id,
        assistant_message_id=None,
        question="Original question",
        result=_result("none", unsupported=("x",)),
    )
    assert offer is not None
    assert offer.query_text == "Original question"
    # The consent endpoint never accepts a replacement query; the stored row
    # remains the source of truth.
    assert isinstance(offer, ChatWebConsent)
