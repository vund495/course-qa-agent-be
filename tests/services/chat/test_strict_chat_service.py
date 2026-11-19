"""Strict-source course chat orchestration without automatic web search."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.chat import ChatWebConsent
from app.services import (
    chat_context_service,
    chat_retrieval_service,
    course_service,
    decision_service,
    document_service,
    rag_service,
    strict_chat_service,
    strict_sources_service,
    web_consent_service,
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


def _decision(*, chunks: tuple = ()) -> rag_service.RetrievalDecision:
    return rag_service.RetrievalDecision(
        question="What does photosynthesis do?",
        class_id="class-a",
        threshold=0.8,
        top_score=0.9,
        source=rag_service.SOURCE_CURRICULUM,
        chunks=chunks,
    )


def _chunk() -> rag_service.ScoredChunk:
    return rag_service.ScoredChunk(
        content="Photosynthesis converts light into chemical energy.",
        score=0.9,
        metadata={
            "document_id": "doc-bio",
            "file_name": "bio.pdf",
            "page_number": 1,
            "section_path": "Biology > Photosynthesis",
        },
    )


def test_class_has_uploaded_documents_counts_pending_and_failed_rows():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        status="pending"
    )
    assert document_service.class_has_uploaded_documents(db, uuid.uuid4()) is True

    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        status="failed"
    )
    assert document_service.class_has_uploaded_documents(db, uuid.uuid4()) is True

    db.query.return_value.filter.return_value.first.return_value = None
    assert document_service.class_has_uploaded_documents(db, uuid.uuid4()) is False


def test_empty_class_returns_exact_message_before_llm_retrieval_or_consent(monkeypatch):
    exact = "Giáo viên chưa tải tài liệu nào cho khóa học này."
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    assistant_id = uuid.uuid4()

    def must_not_call(name):
        def fail(*_args, **_kwargs):
            raise AssertionError(f"{name} must not be called for an empty class")

        return fail

    monkeypatch.setattr(
        document_service,
        "class_has_uploaded_documents",
        lambda *_args, **_kwargs: False,
    )
    for module, name in (
        (course_service, "get_class"),
        (decision_service, "is_confidently_out_of_scope"),
        (chat_context_service, "condense_question"),
        (chat_retrieval_service, "retrieve_for_chat"),
        (strict_sources_service, "generate_strict_sources_answer"),
        (web_consent_service, "expire_pending_offers"),
        (web_consent_service, "create_offer_for_result"),
        (rag_service, "search_internet"),
    ):
        monkeypatch.setattr(module, name, must_not_call(name))
    monkeypatch.setattr(
        strict_chat_service,
        "_persist_turn",
        lambda *_args, **_kwargs: (
            SimpleNamespace(id=session_id),
            SimpleNamespace(id=uuid.uuid4()),
            SimpleNamespace(id=assistant_id),
        ),
    )

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_chat(
                    db=object(),
                    message="What does photosynthesis do?",
                    class_id=uuid.uuid4(),
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        )
    )

    assert [event for event, _ in events] == ["token", "done"]
    assert events[0][1] == {"text": exact}
    done = events[1][1]
    assert done["source"] == "none"
    assert done["strict_status"] == "none"
    assert done["answer_kind"] == "course"
    assert done["used_web_search"] is False
    assert done["consent_offer_id"] is None
    assert not any(event == "citation" for event, _ in events)


def _result(status: str, *, offer: bool = False) -> strict_sources_service.StrictSourcesResult:
    if status == "full":
        return strict_sources_service.StrictSourcesResult(
            question="What does photosynthesis do?",
            status="full",
            answer="- It converts light into chemical energy. [1]",
            intents=[
                strict_sources_service.ValidatedIntent(
                    intent_id="I1",
                    question="What does photosynthesis do?",
                    question_segment="What does photosynthesis do?",
                    status="supported",
                    claim="It converts light into chemical energy.",
                    source_ids=["1"],
                )
            ],
            supported_intent_ids=["I1"],
            source_ids_used=["1"],
        )
    if status == "partial":
        return strict_sources_service.StrictSourcesResult(
            question="What does photosynthesis do and who discovered it?",
            status="partial",
            answer="- It converts light into chemical energy. [1]",
            intents=[
                strict_sources_service.ValidatedIntent(
                    intent_id="I1",
                    question="What does photosynthesis do?",
                    question_segment="What does photosynthesis do and",
                    status="supported",
                    claim="It converts light into chemical energy.",
                    source_ids=["1"],
                ),
                strict_sources_service.ValidatedIntent(
                    intent_id="I2",
                    question="Who discovered it?",
                    question_segment="who discovered it?",
                    status="unsupported",
                    limitation="Not covered.",
                ),
            ],
            supported_intent_ids=["I1"],
            unsupported_intent_ids=["I2"],
            source_ids_used=["1"],
        )
    return strict_sources_service.StrictSourcesResult(
        question="What does photosynthesis do and who discovered it?",
        status="none",
        reason="no_supported_evidence",
        intents=[
            strict_sources_service.ValidatedIntent(
                intent_id="I1",
                question="Who discovered it?",
                question_segment="who discovered it?",
                status="unsupported",
                limitation="Not covered.",
            )
        ],
        unsupported_intent_ids=["I1"],
    )


def _fake_offer(
    *,
    scope_kind: str = "missing",
    conflict_note: str | None = None,
    conflict_citations: list[dict] | None = None,
) -> ChatWebConsent:
    now = datetime.now(UTC)
    return ChatWebConsent(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        assistant_message_id=uuid.uuid4(),
        scope_kind=scope_kind,
        question="What does photosynthesis do and who discovered it?",
        query_text="who discovered it?",
        scope_segments=["who discovered it?"],
        conflict_note=conflict_note,
        conflict_citations=conflict_citations,
        status="pending",
        expires_at=now + timedelta(minutes=30),
    )


def _conflict_result() -> strict_sources_service.StrictSourcesResult:
    return strict_sources_service.StrictSourcesResult(
        question="What does photosynthesis do and who discovered it?",
        status="partial",
        answer="- It converts light into chemical energy. [1]",
        intents=[
            strict_sources_service.ValidatedIntent(
                intent_id="I1",
                question="What does photosynthesis do?",
                question_segment="What does photosynthesis do and",
                status="supported",
                claim="It converts light into chemical energy.",
                source_ids=["1"],
            ),
            strict_sources_service.ValidatedIntent(
                intent_id="I2",
                question="Who discovered it?",
                question_segment="who discovered it?",
                status="conflicting",
                source_ids=["1", "2"],
                conflict_note="Source 1 says early; source 2 says much later.",
            ),
        ],
        supported_intent_ids=["I1"],
        conflicting_intent_ids=["I2"],
        source_ids_used=["1"],
    )


def _patch_common(monkeypatch, *, result, offer=None, chunks=None):
    async def in_scope(**_kwargs):
        return False

    monkeypatch.setattr(decision_service, "is_confidently_out_of_scope", in_scope)
    monkeypatch.setattr(
        course_service,
        "get_class",
        lambda *_args, **_kwargs: SimpleNamespace(
            name="Biology", info=SimpleNamespace(description="Intro biology")
        ),
    )
    monkeypatch.setattr(
        chat_retrieval_service,
        "retrieve_for_chat",
        lambda *_args, **_kwargs: _decision(
            chunks=chunks if chunks is not None else (_chunk(),)
        ),
    )
    monkeypatch.setattr(
        document_service,
        "class_has_uploaded_documents",
        lambda *_args, **_kwargs: True,
    )

    async def fake_strict(**_kwargs):
        return result

    monkeypatch.setattr(strict_sources_service, "generate_strict_sources_answer", fake_strict)
    monkeypatch.setattr(
        web_consent_service,
        "expire_pending_offers",
        lambda *_args, **_kwargs: None,
    )
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    assistant_id = uuid.uuid4()

    def fake_persist(*_args, **_kwargs):
        return (
            SimpleNamespace(id=session_id),
            SimpleNamespace(id=uuid.uuid4()),
            SimpleNamespace(id=assistant_id),
        )

    monkeypatch.setattr(strict_chat_service, "_persist_turn", fake_persist)
    if offer is not None:
        monkeypatch.setattr(
            web_consent_service,
            "create_offer_for_result",
            lambda *_args, **_kwargs: offer,
        )
    return user_id, session_id


def test_full_evidence_streams_only_validated_course_answer_and_citations(monkeypatch) -> None:
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))

    raw = asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=object(),
                message="What does photosynthesis do?",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
            )
        )
    )
    events = _events(raw)
    assert [event for event, _ in events] == [
        "progress",
        "progress",
        "progress",
        "progress",
        "token",
        "citation",
        "done",
    ]
    assert events[4][1]["text"] == "- It converts light into chemical energy. [1]"
    assert events[5][1]["kind"] == "curriculum"
    assert events[5][1]["section"] == "Biology > Photosynthesis"
    assert events[-1][1]["strict_status"] == "full"
    assert events[-1][1]["used_web_search"] is False
    assert events[-1][1]["consent_offer_id"] is None


def test_full_turn_expires_prior_pending_offer(monkeypatch) -> None:
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))
    expired: list[tuple] = []

    def fake_expire(_db, *, user_id, session_id):
        expired.append((user_id, session_id))

    monkeypatch.setattr(web_consent_service, "expire_pending_offers", fake_expire)

    asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=object(),
                message="What does photosynthesis do?",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
            )
        )
    )
    assert expired == [(user_id, session_id)]


def test_out_of_scope_turn_expires_prior_pending_offer(monkeypatch) -> None:
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))
    expired: list[tuple] = []

    def fake_expire(_db, *, user_id, session_id):
        expired.append((user_id, session_id))

    async def out_of_scope(**_kwargs):
        return True

    monkeypatch.setattr(web_consent_service, "expire_pending_offers", fake_expire)
    monkeypatch.setattr(decision_service, "is_confidently_out_of_scope", out_of_scope)

    asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=object(),
                message="What are the lottery numbers?",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
            )
        )
    )
    assert expired == [(user_id, session_id)]


def test_partial_evidence_streams_supported_part_then_missing_scope_offer(monkeypatch) -> None:
    offer = _fake_offer(scope_kind="missing")
    user_id, session_id = _patch_common(monkeypatch, result=_result("partial"), offer=offer)

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_chat(
                    db=object(),
                    message="What does photosynthesis do and who discovered it?",
                    class_id=uuid.uuid4(),
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        )
    )
    consent = [data for event, data in events if event == "consent"]
    assert len(consent) == 1
    assert consent[0]["scope_kind"] == "missing"
    assert consent[0]["query_scope"] == ["who discovered it?"]
    assert events[-1][1]["strict_status"] == "partial"
    assert events[-1][1]["consent_offer_id"] == str(offer.id)
    assert all("who discovered" not in data.get("text", "") for event, data in events if event == "token")


def test_partial_conflict_is_warned_with_both_sides_and_citations(monkeypatch) -> None:
    second_chunk = rag_service.ScoredChunk(
        content="Some sources place the discovery much later.",
        score=0.8,
        metadata={"document_id": "doc-bio-2", "file_name": "bio-2.pdf", "page_number": 4},
    )
    conflict_citations = [
        {
            "index": 1,
            "kind": "curriculum",
            "title": "bio.pdf",
            "url": None,
            "snippet": "source one",
            "document_id": "doc-bio",
            "page": 1,
            "indexes": [1],
            "highlights": [],
        },
        {
            "index": 2,
            "kind": "curriculum",
            "title": "bio-2.pdf",
            "url": None,
            "snippet": "source two",
            "document_id": "doc-bio-2",
            "page": 4,
            "indexes": [2],
            "highlights": [],
        },
    ]
    offer = _fake_offer(
        conflict_note="Source 1 says early; source 2 says much later.",
        conflict_citations=conflict_citations,
    )
    user_id, session_id = _patch_common(
        monkeypatch,
        result=_conflict_result(),
        offer=offer,
        chunks=(_chunk(), second_chunk),
    )

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_chat(
                    db=object(),
                    message="What does photosynthesis do and who discovered it?",
                    class_id=uuid.uuid4(),
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        )
    )
    token_text = "".join(data["text"] for event, data in events if event == "token")
    assert "Source conflict warning" in token_text
    assert "Source 1 says early" in token_text
    assert {data["index"] for event, data in events if event == "citation"} == {1, 2}
    consent = next(data for event, data in events if event == "consent")
    assert "Source 1 says early" in consent["conflict_note"]
    assert {citation["index"] for citation in consent["conflict_citations"]} == {1, 2}


def test_none_asks_for_the_full_question_scope_and_never_searches(monkeypatch) -> None:
    offer = _fake_offer(scope_kind="full")
    user_id, session_id = _patch_common(
        monkeypatch, result=_result("none"), offer=offer, chunks=()
    )

    def must_not_search(*_args, **_kwargs):
        raise AssertionError("The strict chat path must not search the web automatically")

    monkeypatch.setattr(rag_service, "search_internet", must_not_search)

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_chat(
                    db=object(),
                    message="What does photosynthesis do and who discovered it?",
                    class_id=uuid.uuid4(),
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        )
    )
    assert any(event == "consent" and data["scope_kind"] == "full" for event, data in events)
    assert not any(event == "citation" for event, _ in events)
    combined = "".join(data["text"] for event, data in events if event == "token")
    assert combined == strict_chat_service.NO_COURSE_EVIDENCE_MESSAGE
    assert "Giáo viên chưa tải tài liệu nào cho khóa học này." not in combined
    assert events[-1][1]["strict_status"] == "none"


def test_strict_validation_failure_emits_no_answer_token(monkeypatch) -> None:
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))

    async def fail(**_kwargs):
        raise strict_sources_service.StrictSourcesValidationError("invalid evidence")

    monkeypatch.setattr(strict_sources_service, "generate_strict_sources_answer", fail)

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_chat(
                    db=object(),
                    message="What does photosynthesis do?",
                    class_id=uuid.uuid4(),
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        )
    )
    assert [event for event, _ in events] == ["progress", "progress", "progress", "error"]
    assert not any(event in {"token", "citation", "done"} for event, _ in events)


def test_out_of_scope_gate_refuses_before_retrieval(monkeypatch) -> None:
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))

    async def out_of_scope(**_kwargs):
        return True

    monkeypatch.setattr(decision_service, "is_confidently_out_of_scope", out_of_scope)
    monkeypatch.setattr(
        chat_retrieval_service,
        "retrieve_for_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("An out-of-scope question must not be retrieved")
        ),
    )

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_chat(
                    db=object(),
                    message="What are the lottery numbers?",
                    class_id=uuid.uuid4(),
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        )
    )
    assert [event for event, _ in events] == ["progress", "token", "done"]
    assert events[-1][1]["source"] == rag_service.SOURCE_UNRELATED


@pytest.mark.parametrize(
    ("searcher", "expected_log"),
    [
        (lambda _query: [], "no usable web search results"),
        (
            lambda _query: (_ for _ in ()).throw(RuntimeError("search down")),
            "web search failed",
        ),
    ],
)
def test_consent_releases_offer_when_search_has_no_usable_results(
    monkeypatch,
    caplog,
    searcher,
    expected_log,
) -> None:
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        assistant_message_id=uuid.uuid4(),
        query_text="secret-query-should-not-be-logged",
    )
    released: list[object] = []

    monkeypatch.setattr(
        web_consent_service,
        "claim_offer",
        lambda *_args, **_kwargs: (offer, "claimed"),
    )
    monkeypatch.setattr(
        web_consent_service,
        "release_offer",
        lambda _db, *, offer: released.append(offer),
    )
    caplog.set_level(logging.WARNING)

    stream = asyncio.run(
        strict_chat_service.decide_consent(
            db=object(),
            user_id=uuid.uuid4(),
            offer_id=offer.id,
            class_id=uuid.uuid4(),
            session_id=offer.session_id,
            decision="accept",
            search_fn=searcher,
        )
    )
    events = _events(asyncio.run(_collect(stream)))

    assert [event for event, _ in events] == ["progress", "error"]
    assert released == [offer]
    assert expected_log in caplog.text
    assert "no usable fetched web evidence" not in caplog.text
    assert offer.query_text not in caplog.text


async def _collect(stream) -> list[str]:
    return [item async for item in stream]
