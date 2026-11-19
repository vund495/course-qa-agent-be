"""Isolated, SSRF-bounded web evidence and separate web answer path."""

from __future__ import annotations

import asyncio
import json
import logging

import httpcore
import pytest

from app.services import rag_service
from app.services.strict_web_service import (
    WebAnswerGenerationError,
    WebAnswerValidationError,
    WebEvidence,
    WebEvidenceError,
    _PinnedPublicBackend,
    _read_capped_body,
    _resolve_public_target,
    generate_web_answer,
    search_web_evidence,
    validate_public_http_url,
)


def _intent(
    intent_id: str,
    question: str,
    question_segment: str,
    status: str,
    *,
    claim: str = "",
    source_ids: list[str] | None = None,
    limitation: str = "",
    conflict_note: str = "",
) -> dict:
    return {
        "intent_id": intent_id,
        "question": question,
        "question_segment": question_segment,
        "status": status,
        "claim": claim,
        "source_ids": source_ids or [],
        "limitation": limitation,
        "conflict_note": conflict_note,
    }


def _payload(*intents: dict) -> dict:
    return {"intents": list(intents)}


def _evidence() -> tuple[WebEvidence, ...]:
    return (
        WebEvidence(
            source_id="W1",
            title="Official reference",
            url="https://8.8.8.8/reference",
            content="Photosynthesis converts light into chemical energy.",
        ),
        WebEvidence(
            source_id="W2",
            title="Second reference",
            url="https://1.1.1.1/second",
            content="Chlorophyll absorbs light.",
        ),
    )


def test_public_url_validation_rejects_private_local_and_credentialed_targets() -> None:
    assert validate_public_http_url("https://8.8.8.8/reference") == "https://8.8.8.8/reference"
    for url in (
        "http://127.0.0.1/secret",
        "http://localhost/secret",
        "http://10.0.0.1/secret",
        "https://user:pass@8.8.8.8/secret",
        "ftp://8.8.8.8/file",
    ):
        with pytest.raises(WebEvidenceError):
            validate_public_http_url(url)


def test_streamed_body_is_rejected_at_the_hard_byte_cap() -> None:
    class OversizedResponse:
        def iter_stream(self):
            yield b"x" * 100
            yield b"y" * 100

    with pytest.raises(WebEvidenceError, match="byte cap|too large|exceeded"):
        _read_capped_body(OversizedResponse(), max_bytes=150)


def test_pinned_backend_connects_to_validated_ip_not_second_dns_answer(monkeypatch) -> None:
    public = "93.184.216.34"
    private = "10.0.0.7"
    answers = iter([public, private])

    def fake_getaddrinfo(_host, port, *_args, **_kwargs):
        return [(None, None, None, None, (next(answers), port))]

    monkeypatch.setattr("app.services.strict_web_service.socket.getaddrinfo", fake_getaddrinfo)
    _url, host, pinned_ip = _resolve_public_target("https://example.com/page")
    assert pinned_ip == public

    connected: list[str] = []

    def fake_connect_tcp(self, host, port, **_kwargs):
        connected.append(host)
        return object()

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)
    backend = _PinnedPublicBackend(host=host, ip=pinned_ip)
    backend.connect_tcp(host, 443)
    assert connected == [public]
    assert private not in connected


def test_diagnostics_distinguish_no_usable_sources_from_validation_failure(caplog) -> None:
    caplog.set_level(logging.WARNING)
    query = "secret-query-should-not-be-logged"

    with pytest.raises(WebEvidenceError):
        search_web_evidence(
            query,
            search_fn=lambda *_args, **_kwargs: [],
            fetch_fn=lambda _url: "unused",
        )

    assert "no usable fetched sources" in caplog.text
    assert query not in caplog.text

    caplog.clear()

    async def invalid_model(_messages):
        return "not a JSON answer"

    with pytest.raises(WebAnswerValidationError):
        asyncio.run(
            generate_web_answer(
                query_scope=query,
                evidence=_evidence(),
                model_invoker=invalid_model,
            )
        )

    assert "strict web answer validation failed" in caplog.text
    assert "no usable fetched sources" not in caplog.text
    assert query not in caplog.text
    assert "8.8.8.8" not in caplog.text
    assert "Photosynthesis converts" not in caplog.text

    caplog.clear()

    async def failing_model(_messages):
        raise RuntimeError("provider unavailable")

    with pytest.raises(WebAnswerGenerationError):
        asyncio.run(
            generate_web_answer(
                query_scope=query,
                evidence=_evidence(),
                model_invoker=failing_model,
            )
        )

    assert "strict web answer generation failed" in caplog.text
    assert "no usable fetched sources" not in caplog.text
    assert "strict web answer validation failed" not in caplog.text
    assert query not in caplog.text
    assert "8.8.8.8" not in caplog.text
    assert "Photosynthesis converts" not in caplog.text


def test_search_validates_before_fetching_and_drops_private_urls() -> None:
    fetched: list[str] = []

    def search(_query, **_kwargs):
        return [rag_service.WebResult(title="Private", url="http://127.0.0.1/secret", content="")]
    def fetch(url: str) -> str:
        fetched.append(url)
        return "secret"

    with pytest.raises(WebEvidenceError):
        search_web_evidence("query", search_fn=search, fetch_fn=fetch)
    assert fetched == []


def test_search_keeps_only_public_fetched_evidence() -> None:
    def search(_query, **_kwargs):
        return [
            rag_service.WebResult(title="Private", url="http://127.0.0.1/secret", content=""),
            rag_service.WebResult(
                title="Public", url="https://8.8.8.8/reference", content="snippet"
            ),
        ]

    evidence = search_web_evidence(
        "photosynthesis",
        search_fn=search,
        fetch_fn=lambda _url: "Fetched public page about photosynthesis.",
    )
    assert len(evidence) == 1
    assert evidence[0].source_id == "W1"
    assert evidence[0].url == "https://8.8.8.8/reference"


def test_web_answer_uses_only_fetched_evidence_and_returns_links() -> None:
    captured: list[str] = []
    question = "What does photosynthesis do and what absorbs light?"

    async def fake_model(messages):
        captured.extend(str(message.content) for message in messages)
        return json.dumps(
            _payload(
                _intent(
                    "I1",
                    "What does photosynthesis do?",
                    "What does photosynthesis do and",
                    "supported",
                    claim="It converts light into chemical energy.",
                    source_ids=["W1"],
                ),
                _intent(
                    "I2",
                    "What absorbs light?",
                    "what absorbs light?",
                    "supported",
                    claim="Chlorophyll absorbs light.",
                    source_ids=["W2"],
                ),
            )
        )

    result = asyncio.run(
        generate_web_answer(
            query_scope=question,
            evidence=_evidence(),
            model_invoker=fake_model,
        )
    )

    assert result.answer.startswith("**Web Search Answer**")
    assert "chemical energy" in result.answer
    assert "Chlorophyll" in result.answer
    assert [citation.url for citation in result.citations] == [
        "https://8.8.8.8/reference",
        "https://1.1.1.1/second",
    ]
    rendered = "\n".join(captured)
    assert question in rendered
    assert "Photosynthesis converts light into chemical energy." in rendered
    assert "COURSE_SECRET" not in rendered


def test_web_answer_warns_on_conflict_without_selecting_a_winner() -> None:
    async def fake_model(_messages):
        return json.dumps(
            _payload(
                _intent(
                    "I1",
                    "When did it happen?",
                    "When did it happen?",
                    "conflicting",
                    source_ids=["W1", "W2"],
                    conflict_note="W1 says early; W2 says late.",
                )
            )
        )

    result = asyncio.run(
        generate_web_answer(
            query_scope="When did it happen?",
            evidence=_evidence(),
            model_invoker=fake_model,
        )
    )

    assert "Source conflict warning" in result.answer
    assert "W1 says early" in result.answer
    assert len(result.citations) == 2


def test_web_answer_rejects_invalid_source_id_and_insufficient_answer() -> None:
    async def invalid_source(_messages):
        return json.dumps(
            _payload(
                _intent(
                    "I1",
                    "Question",
                    "Question",
                    "unsupported",
                    source_ids=["W99"],
                    limitation="No source.",
                )
            )
        )

    with pytest.raises(WebAnswerValidationError):
        asyncio.run(
            generate_web_answer(
                query_scope="Question",
                evidence=_evidence(),
                model_invoker=invalid_source,
            )
        )

    async def empty_answer(_messages):
        return json.dumps(
            _payload(
                _intent(
                    "I1",
                    "Question",
                    "Question",
                    "unsupported",
                    limitation="No evidence covers this.",
                )
            )
        )

    with pytest.raises(WebAnswerValidationError):
        asyncio.run(
            generate_web_answer(
                query_scope="Question",
                evidence=_evidence(),
                model_invoker=empty_answer,
            )
        )


def test_web_answer_rejects_allowed_but_unrelated_cited_source() -> None:
    unrelated = (
        WebEvidence(
            source_id="W1",
            title="Cafeteria page",
            url="https://8.8.8.8/cafeteria",
            content="The cafeteria opens at noon.",
        ),
    )

    async def fake_model(_messages):
        return json.dumps(
            _payload(
                _intent(
                    "I1",
                    "What is photosynthesis?",
                    "What is photosynthesis?",
                    "unsupported",
                    source_ids=["W1"],
                    limitation="The cited page does not discuss photosynthesis.",
                )
            )
        )

    with pytest.raises(WebAnswerValidationError):
        asyncio.run(
            generate_web_answer(
                query_scope="What is photosynthesis?",
                evidence=unrelated,
                model_invoker=fake_model,
            )
        )


def test_web_answer_rejects_omitted_compound_subquestion() -> None:
    question = "What does photosynthesis do and who discovered it?"

    async def fake_model(_messages):
        return json.dumps(
            _payload(
                _intent(
                    "I1",
                    "What does photosynthesis do?",
                    "What does photosynthesis do and",
                    "supported",
                    claim="It converts light into chemical energy.",
                    source_ids=["W1"],
                )
            )
        )

    with pytest.raises(WebAnswerValidationError):
        asyncio.run(
            generate_web_answer(
                query_scope=question,
                evidence=_evidence(),
                model_invoker=fake_model,
            )
        )


def test_web_answer_rejects_malformed_or_failed_model_output() -> None:
    async def malformed(_messages):
        return "not json"

    with pytest.raises(WebAnswerValidationError):
        asyncio.run(
            generate_web_answer(
                query_scope="Question",
                evidence=_evidence(),
                model_invoker=malformed,
            )
        )

    async def failed(_messages):
        raise RuntimeError("provider down")

    with pytest.raises(WebEvidenceError):
        asyncio.run(
            generate_web_answer(
                query_scope="Question",
                evidence=_evidence(),
                model_invoker=failed,
            )
        )
