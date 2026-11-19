"""Tests for the Gemini Decisions API scope gate."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.services import decision_service


def _answer(
    kind: str,
    *,
    choice: str | None = None,
    confidence: float | None = 0.9,
    noul: float | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        type=kind,
        choice=choice,
        confidence=confidence,
        noul=noul,
    )


def _response(
    verdict: str = "out_of_scope",
    *,
    confidence: float | None = 0.94,
    related: float | None = 0.8,
    homework: float | None = 0.2,
    answers: dict | None = None,
) -> SimpleNamespace:
    if answers is None:
        answers = {
            "verdict": _answer("choice", choice=verdict, confidence=confidence),
            "is_related_tech": _answer("noul", confidence=0.8, noul=related),
            "is_homework_request": _answer("noul", confidence=0.8, noul=homework),
        }
    return SimpleNamespace(answers=answers)


def _use_gemini(monkeypatch, *, response=None, error=None, outcomes=None) -> dict:
    captured: dict = {"calls": [], "clients": []}

    class FakeDecisions:
        async def create(self, **kwargs):
            captured["calls"].append(kwargs)
            if outcomes is not None:
                outcome = outcomes[len(captured["calls"]) - 1]
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            if error is not None:
                raise error
            return response or _response()

    class FakeAio:
        def __init__(self) -> None:
            self.decisions = FakeDecisions()

        async def aclose(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured["clients"].append(kwargs)
            self.aio = FakeAio()

    monkeypatch.setattr(decision_service.genai, "Client", FakeClient)
    monkeypatch.setattr(decision_service.settings, "google_api_key", SecretStr("secret"))
    monkeypatch.setattr(decision_service.settings, "decision_timeout_seconds", 12.0)
    monkeypatch.setattr(decision_service.settings, "decision_key_attempts", 3)
    async def empty_queries(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(decision_service.gateway, "ainvoke_chat", empty_queries)
    return captured


def _class_decision(**overrides):
    arguments = {
        "class_name": "C++ Basic",
        "class_description": "Introductory C++ course",
        "question": "How do Python lists work?",
        "history": "Student: what is a pointer\nAssistant: a pointer holds an address",
    }
    arguments.update(overrides)
    return decision_service.decide_scope(**arguments)


def test_google_genai_sdk_exposes_async_decisions_api() -> None:
    client = decision_service.genai.Client(api_key="test-key")
    try:
        assert callable(client.aio.decisions.create)
    finally:
        asyncio.run(client.aio.aclose())


def test_one_decisions_request_returns_all_three_signals_and_keeps_context(monkeypatch):
    captured = _use_gemini(
        monkeypatch,
        response=_response(confidence=0.93, related=0.75, homework=0.51),
    )

    decision = asyncio.run(
        _class_decision(
            top_chunk_snippet="A Python list is mutable and ordered.",
            has_code=True,
            code_snippet_truncated="items = [1, 2]",
        )
    )

    assert len(captured["calls"]) == 1
    assert captured["calls"][0]["model"] == "gemini-decision-1"
    call_input = captured["calls"][0]["input"]
    for context in (
        "C++ Basic",
        "Introductory C++ course",
        "A Python list is mutable and ordered.",
        "what is a pointer",
        "How do Python lists work?",
        "items = [1, 2]",
    ):
        assert context in call_input

    questions = captured["calls"][0]["questions"]
    assert set(questions) == {"verdict", "is_related_tech", "is_homework_request"}
    assert questions["verdict"]["type"] == "choice"
    assert set(questions["verdict"]["criteria"]) == {
        "core",
        "comparison",
        "extension",
        "logistics",
        "out_of_scope",
    }
    assert questions["is_related_tech"]["type"] == "noul"
    assert questions["is_homework_request"]["type"] == "noul"
    assert captured["clients"][0]["api_key"] == "secret"
    assert captured["clients"][0]["http_options"].api_version == "v1beta"

    assert decision.verdict == "out_of_scope"
    assert decision.confidence == pytest.approx(0.93)
    assert decision.is_related_tech is True
    assert decision.is_homework_request is True
    assert decision.reasoning == ""


@pytest.mark.parametrize(
    "verdict",
    ["core", "comparison", "extension", "logistics", "out_of_scope"],
)
def test_choice_answer_maps_to_scope_verdict(monkeypatch, verdict: str):
    _use_gemini(monkeypatch, response=_response(verdict=verdict))

    decision = asyncio.run(_class_decision())

    assert decision is not None
    assert decision.verdict == verdict


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [(0.79, False), (0.8, True), (0.95, True)],
)
def test_choice_confidence_uses_existing_scope_threshold(monkeypatch, confidence, expected):
    _use_gemini(monkeypatch, response=_response(confidence=confidence))

    decision = asyncio.run(_class_decision())

    assert decision_service._is_confident_out_of_scope(decision) is expected


@pytest.mark.parametrize(
    ("related", "homework", "expected_related", "expected_homework"),
    [(0.49, 0.5, False, True), (0.5, 0.49, True, False)],
)
def test_noul_probabilities_use_half_threshold(
    monkeypatch, related, homework, expected_related, expected_homework
):
    _use_gemini(
        monkeypatch,
        response=_response(related=related, homework=homework),
    )

    decision = asyncio.run(_class_decision())

    assert decision.is_related_tech is expected_related
    assert decision.is_homework_request is expected_homework


@pytest.mark.parametrize(
    "answers",
    [
        {},
        {"verdict": _answer("noul", noul=0.9)},
        {
            "verdict": _answer("choice", choice="unknown", confidence=0.99),
            "is_related_tech": _answer("noul", noul=0.2),
            "is_homework_request": _answer("noul", noul=0.2),
        },
        {
            "verdict": _answer("choice", choice="core", confidence=None),
            "is_related_tech": _answer("noul", noul=0.2),
            "is_homework_request": _answer("noul", noul=0.2),
        },
        {
            "verdict": _answer("choice", choice="core", confidence=0.9),
            "is_related_tech": _answer("noul", noul=1.2),
            "is_homework_request": _answer("noul", noul=0.2),
        },
    ],
)
def test_invalid_or_incomplete_decisions_fail_open(monkeypatch, answers):
    _use_gemini(monkeypatch, response=_response(answers=answers))

    decision = asyncio.run(_class_decision())

    assert decision is None
    assert decision_service._is_confident_out_of_scope(decision) is False


def test_scope_provider_failure_has_no_model_fallback_or_cooldown(monkeypatch):
    captured = _use_gemini(monkeypatch, error=RuntimeError("503 unavailable"))

    first = asyncio.run(_class_decision())
    second = asyncio.run(_class_decision())

    assert first is None
    assert second is None
    assert len(captured["calls"]) == 2
    assert all(call["model"] == "gemini-decision-1" for call in captured["calls"])


def test_key_rotation_retries_next_pool_key(monkeypatch):
    key_ids = [uuid.uuid4(), uuid.uuid4()]
    records = [
        SimpleNamespace(key_id=key_ids[0], key_name="first"),
        SimpleNamespace(key_id=key_ids[1], key_name="second"),
    ]
    resolved: list[set] = []
    failed: list[object] = []
    succeeded: list[object] = []
    captured = _use_gemini(
        monkeypatch,
        outcomes=[RuntimeError("503 unavailable"), _response("core")],
    )
    monkeypatch.setattr(decision_service.settings, "decision_key_attempts", 2)

    def resolve_key(provider, model, db, excluded):
        resolved.append(set(excluded))
        index = len(resolved) - 1
        return f"key-{index + 1}", records[index]

    monkeypatch.setattr(decision_service, "_resolve_key", resolve_key)
    monkeypatch.setattr(
        decision_service,
        "_record_failure",
        lambda provider, db, record, error: failed.append(record),
    )
    monkeypatch.setattr(
        decision_service,
        "_record_success",
        lambda provider, db, record: succeeded.append(record),
    )

    decision = asyncio.run(_class_decision(db=object()))

    assert decision.verdict == "core"
    assert len(captured["calls"]) == 2
    assert failed == [records[0]]
    assert succeeded == [records[1]]
    assert resolved == [set(), {key_ids[0]}]


@pytest.mark.parametrize("payload", ['{"external_search_query":"Python list methods","search_query_en":"Python list operations"}', "invalid"])
def test_scope_queries_use_separate_model_and_fail_open(monkeypatch, payload):
    _use_gemini(monkeypatch, response=_response(verdict="core"))
    calls = []

    async def query_model(db, messages, **kwargs):
        calls.append(kwargs["model"])
        assert "How do Python lists work?" in messages[-1].content
        return payload

    monkeypatch.setattr(decision_service.gateway, "ainvoke_chat", query_model)
    decision = asyncio.run(_class_decision())

    assert calls == ["models/gemini-3.5-flash-lite"]
    assert decision.verdict == "core"
    assert decision.external_search_query == (None if payload == "invalid" else "Python list methods")
    assert decision.search_query_en == (None if payload == "invalid" else "Python list operations")


def test_scope_timeout_fails_open_without_query_generation(monkeypatch):
    captured = _use_gemini(monkeypatch, error=TimeoutError("deadline expired"))

    async def unexpected_query_call(*args, **kwargs):
        pytest.fail("Query model should not run after a scope timeout")

    monkeypatch.setattr(decision_service.gateway, "ainvoke_chat", unexpected_query_call)
    assert asyncio.run(_class_decision()) is None
    assert len(captured["calls"]) == 1
