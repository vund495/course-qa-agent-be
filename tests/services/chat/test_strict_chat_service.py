"""Strict-source course chat orchestration without automatic web search."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.chat import ChatWebConsent
from app.schemas.chat import WebConsentResult
from app.services import (
    chat_context_service,
    chat_retrieval_service,
    course_service,
    decision_service,
    document_answer_service,
    document_service,
    history_service,
    rag_service,
    strict_chat_service,
    strict_sources_service,
    strict_web_service,
    suggestion_service,
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
        (web_consent_service, "create_offer_for_result"),
        (rag_service, "search_internet"),
    ):
        monkeypatch.setattr(module, name, must_not_call(name))
    expired: list[dict] = []
    monkeypatch.setattr(
        web_consent_service,
        "expire_pending_offers",
        lambda *_args, **kwargs: expired.append(kwargs),
    )
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
    assert expired == [{"user_id": user_id, "session_id": session_id}]


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

    async def no_suggestions(**_kwargs):
        return []

    monkeypatch.setattr(
        suggestion_service, "generate_followup_questions", no_suggestions
    )
    monkeypatch.setattr(
        suggestion_service, "build_fallback_followups", lambda **_kwargs: []
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


def test_course_lane_gates_reranked_chunks_before_source_validation(monkeypatch):
    original = _chunk()
    chunks = (original, rag_service.ScoredChunk(content="Other", score=0.7, metadata={}))
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"), chunks=chunks)
    calls = []

    async def filter_chunks(*, question, chunks, db):
        calls.append((question, chunks))
        return (original,)

    async def validate(*, question, sources, **_kwargs):
        assert [source.content for source in sources] == [original.content]
        return _result("full")

    monkeypatch.setattr(decision_service, "filter_reranked_chunks", filter_chunks, raising=False)
    monkeypatch.setattr(strict_sources_service, "generate_strict_sources_answer", validate)

    raw = asyncio.run(_collect(strict_chat_service.stream_chat(
        db=object(),
        message="What does photosynthesis do?",
        class_id=uuid.uuid4(),
        user_id=user_id,
        session_id=session_id,
    )))

    assert calls == [("What does photosynthesis do?", chunks)]
    assert _events(raw)[-1][0] == "done"

def test_document_answer_prompt_keeps_code_blocks_without_old_history():
    messages = document_answer_service.build_document_answer_messages(
        question="Show a C++ Hello World example",
        chunks=(_chunk(),),
        source_ids=("1",),
    )

    system_prompt = messages[0].content
    user_prompt = messages[1].content
    assert "fenced code blocks" in system_prompt
    assert "Conversation So Far" in user_prompt
    assert "Show a C++ Hello World example" in user_prompt
    assert "[1]" in user_prompt
    assert "(No previous conversation.)" in user_prompt


def test_stream_uses_document_answer_composer_for_code_example(monkeypatch):
    captured: dict = {}

    async def compose(db, *, question, chunks, source_ids, **_kwargs):
        captured.update(
            question=question,
            chunks=tuple(chunks),
            source_ids=tuple(source_ids),
        )
        return (
            'Below is the standard C++ program [1]:\n\n'
            "```cpp\n#include <iostream>\nint main() {\n"
            '    std::cout << "Hello, World!" << std::endl;\n    return 0;\n}\n```'
        )

    monkeypatch.setattr(document_answer_service, "compose_document_answer", compose)
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))

    async def condense(_history, question, **_kwargs):
        captured["condense_called"] = True
        return question

    monkeypatch.setattr(chat_context_service, "condense_question", condense)
    history = [
        chat_context_service.ConversationExchange(
            user="What is C++?",
            assistant="A compiled language.",
        )
    ]

    raw = asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=MagicMock(),
                message="Show a C++ Hello World example",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
                history=history,
            )
        )
    )
    events = _events(raw)
    token_text = "".join(data["text"] for event, data in events if event == "token")

    assert "```cpp" in token_text
    assert "Hello, World!" in token_text
    assert captured["question"] == "Show a C++ Hello World example"
    assert captured["source_ids"] == ("1",)
    assert captured["condense_called"] is True
    assert "history" not in captured
    assert events[-1][0] == "done"


def test_partial_composer_only_answers_supported_intents(monkeypatch):
    captured: dict = {}

    async def compose(db, *, question, chunks, source_ids, **_kwargs):
        captured.update(question=question, source_ids=tuple(source_ids))
        return "Only the supported part is answered [1]."

    monkeypatch.setattr(document_answer_service, "compose_document_answer", compose)
    user_id, session_id = _patch_common(monkeypatch, result=_result("partial"))

    raw = asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=MagicMock(),
                message="What does photosynthesis do and who discovered it?",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
            )
        )
    )
    token_text = "".join(
        data["text"] for event, data in _events(raw) if event == "token"
    )

    assert captured["question"] == "What does photosynthesis do and"
    assert "who discovered it" not in captured["question"]
    assert captured["source_ids"] == ("1",)
    assert "Only the supported part is answered" in token_text


def test_missing_source_id_does_not_fall_back_to_every_chunk():
    with pytest.raises(document_answer_service.DocumentAnswerError):
        document_answer_service.build_document_answer_messages(
            question="What does photosynthesis do?",
            chunks=(_chunk(),),
            source_ids=("99",),
        )
    with pytest.raises(document_answer_service.DocumentAnswerError):
        document_answer_service.build_document_answer_messages(
            question="What does photosynthesis do?",
            chunks=(_chunk(),),
            source_ids=(),
        )


def test_stream_missing_source_id_keeps_validated_draft(monkeypatch):
    bad = strict_sources_service.StrictSourcesResult(
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
                source_ids=["99"],
            )
        ],
        supported_intent_ids=["I1"],
        source_ids_used=["99"],
    )

    async def validate(**_kwargs):
        return bad

    monkeypatch.setattr(document_answer_service, "compose_document_answer", lambda *a, **k: None)
    user_id, session_id = _patch_common(monkeypatch, result=bad)
    monkeypatch.setattr(strict_sources_service, "generate_strict_sources_answer", validate)

    raw = asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=MagicMock(),
                message="What does photosynthesis do?",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
            )
        )
    )
    token_text = "".join(
        data["text"] for event, data in _events(raw) if event == "token"
    )
    assert "It converts light into chemical energy." in token_text


def test_homework_keeps_validated_draft_without_composer(monkeypatch):
    calls: list = []

    async def compose(**kwargs):
        calls.append(kwargs)
        return "Composer must not run for homework."

    monkeypatch.setattr(document_answer_service, "compose_document_answer", compose)
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))

    raw = asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=MagicMock(),
                message="Giải bài tập này giúp em với",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
            )
        )
    )
    token_text = "".join(
        data["text"] for event, data in _events(raw) if event == "token"
    )

    assert calls == []
    assert "It converts light into chemical energy." in token_text


def test_composer_timeout_keeps_validated_draft(monkeypatch):
    async def timeout_compose(**_kwargs):
        raise TimeoutError("composer timed out")

    monkeypatch.setattr(document_answer_service, "compose_document_answer", timeout_compose)
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))

    raw = asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=MagicMock(),
                message="What does photosynthesis do?",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
            )
        )
    )
    token_text = "".join(
        data["text"] for event, data in _events(raw) if event == "token"
    )
    assert "It converts light into chemical energy." in token_text

def test_composer_enforces_its_timeout(monkeypatch):
    async def slow_invoke(*_args, **_kwargs):
        await asyncio.sleep(5)
        return "late answer"

    monkeypatch.setattr(document_answer_service.gateway, "ainvoke_chat", slow_invoke)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(
            document_answer_service.compose_document_answer(
                MagicMock(),
                question="What does photosynthesis do?",
                chunks=(_chunk(),),
                source_ids=("1",),
                timeout_seconds=0.01,
            )
        )


def test_composer_ignores_array_indexes_inside_code_fences(monkeypatch):
    async def code_answer(*_args, **_kwargs):
        return (
            "Use an array [1]:\n\n"
            "```cpp\nint values[10];\nvalues[0] = 1;\n```\n"
            "The array stores ten values [1]."
        )

    monkeypatch.setattr(document_answer_service.gateway, "ainvoke_chat", code_answer)

    answer = asyncio.run(
        document_answer_service.compose_document_answer(
            MagicMock(),
            question="Show a C++ array example",
            chunks=(_chunk(),),
            source_ids=("1",),
        )
    )
    assert "int values[10]" in answer


def test_composer_rejects_grouped_marker_outside_validated_sources(monkeypatch):
    async def wrong_marker(*_args, **_kwargs):
        return "Answer citing an allowed and a foreign source [1, 99]."

    monkeypatch.setattr(document_answer_service.gateway, "ainvoke_chat", wrong_marker)

    with pytest.raises(document_answer_service.DocumentAnswerError):
        asyncio.run(
            document_answer_service.compose_document_answer(
                MagicMock(),
                question="What does photosynthesis do?",
                chunks=(_chunk(),),
                source_ids=("1",),
            )
        )


def test_web_source_links_requires_a_valid_host():
    sources = [
        rag_service.Source(
            index=1,
            kind=rag_service.SOURCE_INTERNET,
            title="Script",
            url="javascript:alert(1)",
        ),
        rag_service.Source(
            index=2,
            kind=rag_service.SOURCE_INTERNET,
            title="Valid",
            url="https://example.com/cpp",
        ),
        rag_service.Source(
            index=3,
            kind=rag_service.SOURCE_INTERNET,
            title="No host",
            url="https:///missing-host",
        ),
    ]

    links = strict_chat_service._web_source_links(sources)
    assert [source.url for source in links] == ["https://example.com/cpp"]

def test_web_consent_without_markers_emits_and_persists_source_links(monkeypatch):
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        assistant_message_id=uuid.uuid4(),
        query_text="C++ Hello World example",
        status="processing",
    )
    sources = [
        rag_service.Source(
            index=1,
            kind=rag_service.SOURCE_INTERNET,
            title="C++ documentation",
            url="https://example.com/cpp-hello",
            snippet="The standard Hello World program.",
        ),
        rag_service.Source(
            index=2,
            kind=rag_service.SOURCE_INTERNET,
            title="Duplicate result",
            url="https://example.com/cpp-hello",
            snippet="Same URL should be deduplicated.",
        ),
    ]
    persisted: dict = {}

    monkeypatch.setattr(
        web_consent_service, "claim_offer", lambda *_a, **_k: (offer, "claimed")
    )
    monkeypatch.setattr(web_consent_service, "complete_offer", lambda *_a, **_k: None)
    monkeypatch.setattr(web_consent_service, "release_offer", lambda *_a, **_k: None)
    switched: list[tuple] = []
    monkeypatch.setattr(
        history_service,
        "update_content_gap_source",
        lambda *args, **kwargs: switched.append((args, kwargs)),
    )
    monkeypatch.setattr(
        strict_web_service,
        "search_web_evidence",
        lambda *_a, **_k: [
            SimpleNamespace(
                source_id="1",
                title="C++ documentation",
                url="https://example.com/cpp-hello",
                content="The standard Hello World program.",
            )
        ],
    )
    monkeypatch.setattr(
        rag_service,
        "prepare_web_answer",
        lambda *_a, **_k: (sources, "system prompt", "user prompt"),
    )

    async def answer_without_markers(*_args, **_kwargs):
        yield "Below is the standard C++ program."

    monkeypatch.setattr(strict_chat_service.gateway, "astream_chat", answer_without_markers)

    def append_message(db, **kwargs):
        persisted.update(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), citations=kwargs["citations"])

    monkeypatch.setattr(history_service, "append_message", append_message)

    suggestion_calls: dict = {}

    async def web_suggestions(**kwargs):
        suggestion_calls.update(kwargs)
        return ["What about std::endl?"]

    monkeypatch.setattr(
        suggestion_service, "generate_followup_questions", web_suggestions
    )

    async def run_accept():
        outcome = await strict_chat_service.decide_consent(
            db=MagicMock(),
            user_id=uuid.uuid4(),
            offer_id=offer.id,
            class_id=uuid.uuid4(),
            session_id=offer.session_id,
            decision="accept",
            search_fn=lambda _query: [
                rag_service.WebResult(
                    title="C++ documentation",
                    url="https://example.com/cpp-hello",
                    content="The standard Hello World program.",
                )
            ],
        )
        assert not isinstance(outcome, WebConsentResult)
        raw = await _collect(outcome)
        await strict_chat_service.wait_for_content_gap_tasks(timeout=2.0)
        return raw

    events = _events(asyncio.run(run_accept()))
    citations = [data for event, data in events if event == "citation"]

    assert citations
    assert [citation["url"] for citation in citations] == ["https://example.com/cpp-hello"]
    assert persisted["citations"][0]["url"] == "https://example.com/cpp-hello"
    assert persisted["suggested_questions"] == ["What about std::endl?"]
    assert [data for event, data in events if event == "suggestions"] == [
        {"questions": ["What about std::endl?"]}
    ]
    assert events[-1][1]["suggested_questions"] == ["What about std::endl?"]
    assert suggestion_calls["history"] == ""
    assert suggestion_calls["question"] == "C++ Hello World example"
    assert suggestion_calls["chunks"][0].content == "The standard Hello World program."
    assert events[-1][0] == "done"
    assert switched == [
        ((), {"message_id": str(offer.assistant_message_id), "source": "web"}),
    ]

def test_full_answer_restores_followup_suggestions(monkeypatch):
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))

    async def suggestions(**_kwargs):
        return ["What is the next step?", "Can you show an example?"]

    monkeypatch.setattr(suggestion_service, "generate_followup_questions", suggestions)

    raw = asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=MagicMock(),
                message="What does photosynthesis do?",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
            )
        )
    )
    events = _events(raw)

    suggestion_events = [data for event, data in events if event == "suggestions"]
    assert suggestion_events == [
        {"questions": ["What is the next step?", "Can you show an example?"]}
    ]
    done = events[-1][1]
    assert done["suggested_questions"] == [
        "What is the next step?",
        "Can you show an example?",
    ]
    assert done["suggestions"] == done["suggested_questions"]


def test_none_answer_does_not_add_followup_suggestions(monkeypatch):
    async def must_not_generate(**_kwargs):
        raise AssertionError("The no-evidence path must not generate suggestions")

    user_id, session_id = _patch_common(
        monkeypatch, result=_result("none"), offer=_fake_offer()
    )
    monkeypatch.setattr(
        suggestion_service, "generate_followup_questions", must_not_generate
    )

    raw = asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=MagicMock(),
                message="What does photosynthesis do?",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
            )
        )
    )
    events = _events(raw)

    assert not [data for event, data in events if event == "suggestions"]
    assert events[-1][1]["suggested_questions"] == []


def test_web_answer_history_keeps_original_question_and_teacher_action():
    from app.models.chat import ChatMessage

    session_id = uuid.uuid4()
    user = ChatMessage(
        session_id=session_id,
        role="USER",
        content="How do I print Hello World in C++?",
        used_web_search=False,
    )
    course = ChatMessage(
        session_id=session_id,
        role="ASSISTANT",
        content="Use std::cout.",
        used_web_search=False,
        parent_message=user,
    )
    web = ChatMessage(
        session_id=session_id,
        role="ASSISTANT",
        content="A web answer.",
        used_web_search=True,
        parent_message=course,
    )

    assert course.original_question == "How do I print Hello World in C++?"
    assert web.original_question == "How do I print Hello World in C++?"
    assert web.can_create_feedback_ticket is True
    assert user.original_question is None

def test_slow_suggestions_do_not_skip_persist_or_done(monkeypatch):
    async def slow_suggestions(**_kwargs):
        await asyncio.sleep(1)
        return ["late suggestion"]

    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))
    monkeypatch.setattr(
        suggestion_service, "generate_followup_questions", slow_suggestions
    )
    monkeypatch.setattr(
        strict_chat_service, "SUGGESTION_PREFETCH_GRACE_SECONDS", 0.01
    )

    raw = asyncio.run(
        _collect(
            strict_chat_service.stream_chat(
                db=MagicMock(),
                message="What does photosynthesis do?",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
            )
        )
    )
    events = _events(raw)

    assert events[-1][0] == "done"
    assert events[-1][1]["assistant_message_id"]
    assert events[-1][1]["suggested_questions"] == []


def test_web_source_links_skips_malformed_urls_and_ports():
    sources = [
        rag_service.Source(
            index=1,
            kind=rag_service.SOURCE_INTERNET,
            title="Malformed",
            url="http://[invalid",
        ),
        rag_service.Source(
            index=2,
            kind=rag_service.SOURCE_INTERNET,
            title="Bad port",
            url="https://example.com:99999/cpp",
        ),
        rag_service.Source(
            index=3,
            kind=rag_service.SOURCE_INTERNET,
            title="Valid",
            url="https://example.com/cpp",
        ),
    ]

    links = strict_chat_service._web_source_links(sources)
    assert [source.url for source in links] == ["https://example.com/cpp"]


def test_course_turn_reuses_retrieval_vector_and_first_token_timing(monkeypatch):
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))

    def decision_with_vector(*_args, **_kwargs):
        return rag_service.RetrievalDecision(
            question="What does photosynthesis do?",
            class_id="class-a",
            threshold=0.8,
            top_score=0.9,
            source=rag_service.SOURCE_CURRICULUM,
            chunks=(_chunk(),),
            query_vector=(0.11, 0.22),
        )

    monkeypatch.setattr(chat_retrieval_service, "retrieve_for_chat", decision_with_vector)
    persisted: dict = {}
    telemetry_calls: list[dict] = []

    def fake_sync(**kwargs):
        telemetry_calls.append(kwargs)

    monkeypatch.setattr(history_service, "sync_content_gap_query", fake_sync)

    def capture(*_args, **kwargs):
        persisted.update(kwargs)
        return (
            SimpleNamespace(id=session_id),
            SimpleNamespace(id=uuid.uuid4()),
            SimpleNamespace(id=uuid.uuid4()),
        )

    monkeypatch.setattr(strict_chat_service, "_persist_turn", capture)

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

    assert events[-1][0] == "done"
    asyncio.run(strict_chat_service.wait_for_content_gap_tasks(timeout=1.0))
    assert telemetry_calls and telemetry_calls[0]["embedding"] == [0.11, 0.22]
    assert persisted["query_embedding"] == [0.11, 0.22]
    assert isinstance(persisted["thinking_ms"], int)
    assert persisted["thinking_ms"] >= 0
    assert persisted["fallback_reason"] is None
    assert any(
        item.startswith("pedagogy:") for item in persisted["trace"]
    )


def test_none_turn_marks_no_results_without_creating_a_web_vector(monkeypatch):
    offer = _fake_offer()
    user_id, session_id = _patch_common(
        monkeypatch,
        result=_result("none"),
        offer=offer,
        chunks=(),
    )
    persisted: dict = {}

    def capture(*_args, **kwargs):
        persisted.update(kwargs)
        return (
            SimpleNamespace(id=session_id),
            SimpleNamespace(id=uuid.uuid4()),
            SimpleNamespace(id=offer.assistant_message_id),
        )

    monkeypatch.setattr(strict_chat_service, "_persist_turn", capture)
    switched: list[tuple] = []
    monkeypatch.setattr(
        history_service,
        "update_content_gap_source",
        lambda *args, **kwargs: switched.append((args, kwargs)),
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

    assert events[-1][0] == "done"
    assert persisted["query_embedding"] is None
    assert persisted["fallback_reason"] == "no_results"
    assert switched == []


def test_syllabus_question_adds_published_roadmap_to_strict_sources(monkeypatch):
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))
    roadmap = rag_service.ScoredChunk(
        content="### Structured Course Syllabus Roadmap (Authoritative Source):\n- Unit 1: Photosynthesis",
        score=1.0,
        metadata={"document_id": "syllabus-doc", "file_name": "syllabus.xlsx"},
    )
    monkeypatch.setattr(
        strict_chat_service,
        "_is_syllabus_relevant_question",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        strict_chat_service,
        "_format_syllabus_roadmap",
        lambda *_args, **_kwargs: ("roadmap", roadmap),
    )
    monkeypatch.setattr(
        document_service,
        "retrievable_document_ids",
        lambda *_args, **_kwargs: {"syllabus-doc"},
    )
    captured: dict = {}

    async def strict_with_capture(**kwargs):
        captured["sources"] = kwargs["sources"]
        return _result("full")

    monkeypatch.setattr(
        strict_sources_service, "generate_strict_sources_answer", strict_with_capture
    )

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_chat(
                    db=object(),
                    message="How many units are in the syllabus?",
                    class_id=uuid.uuid4(),
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        )
    )

    assert events[-1][0] == "done"
    assert captured["sources"][0].document_id == "syllabus-doc"
    assert "Structured Course Syllabus Roadmap" in captured["sources"][0].content


def test_web_qdrant_update_failure_still_emits_done(monkeypatch):
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        assistant_message_id=uuid.uuid4(),
        query_text="C++ Hello World example",
        status="processing",
    )
    source = rag_service.Source(
        index=1,
        kind=rag_service.SOURCE_INTERNET,
        title="C++ documentation",
        url="https://example.com/cpp-hello",
        snippet="The standard Hello World program.",
    )
    monkeypatch.setattr(web_consent_service, "release_offer", lambda *_a, **_k: None)
    monkeypatch.setattr(web_consent_service, "complete_offer", lambda *_a, **_k: None)
    monkeypatch.setattr(
        strict_web_service,
        "search_web_evidence",
        lambda *_a, **_k: [
            SimpleNamespace(
                source_id="1",
                title="C++ documentation",
                url="https://example.com/cpp-hello",
                content="The standard Hello World program.",
            )
        ],
    )
    monkeypatch.setattr(
        rag_service,
        "prepare_web_answer",
        lambda *_a, **_k: ([source], "system prompt", "user prompt"),
    )

    async def answer(*_args, **_kwargs):
        yield "Below is the standard C++ program."

    monkeypatch.setattr(strict_chat_service.gateway, "astream_chat", answer)

    async def no_suggestions(**_kwargs):
        return []

    monkeypatch.setattr(
        suggestion_service, "generate_followup_questions", no_suggestions
    )
    monkeypatch.setattr(
        suggestion_service, "build_fallback_followups", lambda **_kwargs: []
    )
    persisted: dict = {}

    def append_message(_db, **kwargs):
        persisted.update(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), citations=kwargs["citations"])

    monkeypatch.setattr(history_service, "append_message", append_message)

    def qdrant_down(*_args, **_kwargs):
        raise RuntimeError("Qdrant unreachable")

    monkeypatch.setattr(history_service, "update_content_gap_source", qdrant_down)

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_web_consent(
                    db=MagicMock(),
                    offer=offer,
                    search_fn=lambda _query: [
                        rag_service.WebResult(
                            title="C++ documentation",
                            url="https://example.com/cpp-hello",
                            content="The standard Hello World program.",
                        )
                    ],
                )
            )
        )
    )

    assert events[-1][0] == "done"
    assert events[-1][1]["used_web_search"] is True
    assert persisted["content"] == "Below is the standard C++ program."
    assert persisted["used_web_search"] is True
    assert isinstance(persisted["thinking_ms"], int)
    assert persisted["trace"][0].startswith("pedagogy:")


def test_chit_chat_quick_response_skips_retrieval_scope_and_consent(monkeypatch):
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    assistant_id = uuid.uuid4()

    def must_not_call(name):
        def blocked(*_args, **_kwargs):
            raise AssertionError(f"{name} must not run for chit-chat")

        return blocked

    for module, name in (
        (document_service, "class_has_uploaded_documents"),
        (course_service, "get_class"),
        (decision_service, "is_confidently_out_of_scope"),
        (chat_retrieval_service, "retrieve_for_chat"),
        (strict_sources_service, "generate_strict_sources_answer"),
        (web_consent_service, "create_offer_for_result"),
        (rag_service, "search_internet"),
    ):
        monkeypatch.setattr(module, name, must_not_call(name))
    expired: list[dict] = []
    monkeypatch.setattr(
        web_consent_service,
        "expire_pending_offers",
        lambda *_args, **kwargs: expired.append(kwargs),
    )
    persisted: dict = {}

    def capture(*_args, **kwargs):
        persisted.update(kwargs)
        return (
            SimpleNamespace(id=session_id),
            SimpleNamespace(id=uuid.uuid4()),
            SimpleNamespace(id=assistant_id),
        )

    monkeypatch.setattr(strict_chat_service, "_persist_turn", capture)

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_chat(
                    db=object(),
                    message="hello",
                    class_id=uuid.uuid4(),
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        )
    )

    tokens = "".join(data["text"] for event, data in events if event == "token")
    assert tokens
    assert events[-1][0] == "done"
    assert events[-1][1]["source"] == "conversation"
    assert events[-1][1]["session_id"] == str(session_id)
    assert persisted["excluded_from_context"] is True
    assert persisted["thinking_ms"] == 0
    assert any(
        item.startswith("pedagogy:") for item in persisted["trace"]
    )
    assert expired == [{"user_id": user_id, "session_id": session_id}]


def test_hidden_or_other_class_roadmap_is_not_added_to_strict_sources(monkeypatch):
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))
    roadmap = rag_service.ScoredChunk(
        content="### Structured Course Syllabus Roadmap (Authoritative Source):\n- Unit 1: Hidden",
        score=1.0,
        metadata={"document_id": "hidden-syllabus", "file_name": "hidden.xlsx"},
    )
    monkeypatch.setattr(
        strict_chat_service,
        "_is_syllabus_relevant_question",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        strict_chat_service,
        "_format_syllabus_roadmap",
        lambda *_args, **_kwargs: ("roadmap", roadmap),
    )
    monkeypatch.setattr(
        document_service,
        "retrievable_document_ids",
        lambda *_args, **_kwargs: {"visible-doc"},
    )
    captured: dict = {}

    async def strict_with_capture(**kwargs):
        captured["sources"] = kwargs["sources"]
        return _result("full")

    monkeypatch.setattr(
        strict_sources_service, "generate_strict_sources_answer", strict_with_capture
    )

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_chat(
                    db=object(),
                    message="How many units are in the syllabus?",
                    class_id=uuid.uuid4(),
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        )
    )

    assert events[-1][0] == "done"
    assert all(source.document_id != "hidden-syllabus" for source in captured["sources"])


def test_syllabus_roadmap_keeps_retrieved_chunks_from_the_same_document(monkeypatch):
    syllabus_chunk = rag_service.ScoredChunk(
        content="Published syllabus section with unit outcomes.",
        score=0.9,
        metadata={"document_id": "syllabus-doc", "file_name": "syllabus.xlsx"},
    )
    user_id, session_id = _patch_common(
        monkeypatch, result=_result("full"), chunks=(syllabus_chunk,)
    )
    roadmap = rag_service.ScoredChunk(
        content="### Structured Course Syllabus Roadmap (Authoritative Source):\n- Unit 1: Outcomes",
        score=1.0,
        metadata={"document_id": "syllabus-doc", "file_name": "syllabus.xlsx"},
    )
    monkeypatch.setattr(
        strict_chat_service,
        "_is_syllabus_relevant_question",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        strict_chat_service,
        "_format_syllabus_roadmap",
        lambda *_args, **_kwargs: ("roadmap", roadmap),
    )
    monkeypatch.setattr(
        document_service,
        "retrievable_document_ids",
        lambda *_args, **_kwargs: {"syllabus-doc"},
    )
    captured: dict = {}

    async def strict_with_capture(**kwargs):
        captured["sources"] = kwargs["sources"]
        return _result("full")

    monkeypatch.setattr(
        strict_sources_service, "generate_strict_sources_answer", strict_with_capture
    )

    events = _events(
        asyncio.run(
            _collect(
                strict_chat_service.stream_chat(
                    db=object(),
                    message="How many units are in the syllabus and what outcomes?",
                    class_id=uuid.uuid4(),
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        )
    )

    assert events[-1][0] == "done"
    contents = [source.content for source in captured["sources"]]
    assert "Structured Course Syllabus Roadmap" in contents[0]
    assert any("Published syllabus section" in content for content in contents)


def test_slow_course_telemetry_does_not_block_done(monkeypatch):
    user_id, session_id = _patch_common(monkeypatch, result=_result("full"))

    def decision_with_vector(*_args, **_kwargs):
        return rag_service.RetrievalDecision(
            question="What does photosynthesis do?",
            class_id="class-a",
            threshold=0.8,
            top_score=0.9,
            source=rag_service.SOURCE_CURRICULUM,
            chunks=(_chunk(),),
            query_vector=(0.11, 0.22),
        )

    monkeypatch.setattr(chat_retrieval_service, "retrieve_for_chat", decision_with_vector)
    started = threading.Event()
    finish = threading.Event()
    calls: list[dict] = []

    def slow_sync(**kwargs):
        started.set()
        finish.wait(timeout=1.0)
        calls.append(kwargs)

    monkeypatch.setattr(history_service, "sync_content_gap_query", slow_sync)
    monkeypatch.setattr(history_service, "get_qdrant_client", lambda: MagicMock())

    async def run():
        before = time.monotonic()
        raw = await _collect(
            strict_chat_service.stream_chat(
                db=object(),
                message="What does photosynthesis do?",
                class_id=uuid.uuid4(),
                user_id=user_id,
                session_id=session_id,
                timeout_seconds=1.0,
            )
        )
        elapsed = time.monotonic() - before
        for _ in range(10):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        telemetry_started = started.is_set()
        finish.set()
        await strict_chat_service.wait_for_content_gap_tasks(timeout=1.0)
        return raw, elapsed, telemetry_started

    raw, elapsed, telemetry_started = asyncio.run(run())
    events = _events(raw)

    assert events[-1][0] == "done"
    assert all(event != "error" for event, _ in events)
    assert elapsed < 0.5
    assert telemetry_started is True
    assert calls == [] or calls[0]["message_id"] == events[-1][1]["assistant_message_id"]


def test_slow_web_telemetry_does_not_block_done(monkeypatch):
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        assistant_message_id=uuid.uuid4(),
        query_text="C++ Hello World example",
        status="processing",
    )
    source = rag_service.Source(
        index=1,
        kind=rag_service.SOURCE_INTERNET,
        title="C++ documentation",
        url="https://example.com/cpp-hello",
        snippet="The standard Hello World program.",
    )
    monkeypatch.setattr(web_consent_service, "release_offer", lambda *_a, **_k: None)
    monkeypatch.setattr(web_consent_service, "complete_offer", lambda *_a, **_k: None)
    monkeypatch.setattr(
        strict_web_service,
        "search_web_evidence",
        lambda *_a, **_k: [
            SimpleNamespace(
                source_id="1",
                title="C++ documentation",
                url="https://example.com/cpp-hello",
                content="The standard Hello World program.",
            )
        ],
    )
    monkeypatch.setattr(
        rag_service,
        "prepare_web_answer",
        lambda *_a, **_k: ([source], "system prompt", "user prompt"),
    )

    async def answer(*_args, **_kwargs):
        yield "Below is the standard C++ program."

    monkeypatch.setattr(strict_chat_service.gateway, "astream_chat", answer)

    async def no_suggestions(**_kwargs):
        return []

    monkeypatch.setattr(
        suggestion_service, "generate_followup_questions", no_suggestions
    )
    monkeypatch.setattr(
        suggestion_service, "build_fallback_followups", lambda **_kwargs: []
    )
    monkeypatch.setattr(
        history_service,
        "append_message",
        lambda _db, **kwargs: SimpleNamespace(id=uuid.uuid4(), citations=kwargs["citations"]),
    )
    started = threading.Event()
    finish = threading.Event()

    def slow_update(*_args, **_kwargs):
        started.set()
        finish.wait(timeout=1.0)

    monkeypatch.setattr(history_service, "update_content_gap_source", slow_update)
    monkeypatch.setattr(history_service, "get_qdrant_client", lambda: MagicMock())

    async def run():
        before = time.monotonic()
        raw = await _collect(
            strict_chat_service.stream_web_consent(
                db=MagicMock(),
                offer=offer,
                timeout_seconds=0.5,
                search_fn=lambda _query: [
                    rag_service.WebResult(
                        title="C++ documentation",
                        url="https://example.com/cpp-hello",
                        content="The standard Hello World program.",
                    )
                ],
            )
        )
        elapsed = time.monotonic() - before
        for _ in range(10):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        telemetry_started = started.is_set()
        finish.set()
        await strict_chat_service.wait_for_content_gap_tasks(timeout=1.0)
        return raw, elapsed, telemetry_started

    raw, elapsed, telemetry_started = asyncio.run(run())
    events = _events(raw)

    assert events[-1][0] == "done"
    assert all(event != "error" for event, _ in events)
    assert elapsed < 0.5
    assert telemetry_started is True
