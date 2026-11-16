"""AI-190 budget selection and provider boundary contracts."""

import asyncio
from dataclasses import replace

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.services import token_budget_service as budget


class Counter:
    input_limit = 100000
    output_limit = 10000
    model = "test-model"

    async def count(self, text):
        return len(text.encode("utf-8"))


def render(history, sources):
    return [
        SystemMessage(content="rules"),
        HumanMessage(
            content="Question: keep me\n"
            + "\n".join(history)
            + "\n"
            + "\n".join(f"[{i}] {s.content}" for i, s in enumerate(sources, 1))
        ),
    ]


def limits(**kwargs):
    return replace(
        budget.BudgetLimits(input=180, system=30, history=60, documents=100, answer=20, margin=10),
        **kwargs,
    )


def test_twenty_turn_history_drops_oldest_first_and_preserves_question(caplog):
    history = [f"Student {i}: question\nAssistant {i}: answer" for i in range(20)]
    result = asyncio.run(budget.fit_prompt(render, history, [], Counter(), limits()))
    text = result.messages[1].content
    assert "Student 0:" not in text
    assert "Student 19:" in text
    assert "Question: keep me" in text
    assert result.tokens <= 180
    assert result.history == history[-len(result.history) :]
    assert "history" in caplog.text


def test_drops_low_score_before_high_score_and_renumbers():
    sources = [budget.ContextSource("l" * 70, 0.1), budget.ContextSource("h" * 70, 0.9)]
    result = asyncio.run(budget.fit_prompt(render, [], sources, Counter(), limits()))
    assert result.sources[0].content.startswith("h")
    assert "l" * 30 not in result.messages[1].content
    assert "[1]" in result.messages[1].content


def test_truncates_single_source_and_keeps_identity():
    source = budget.ContextSource("á" * 300, 1, identity="doc-1")
    result = asyncio.run(budget.fit_prompt(render, [], [source], Counter(), limits()))
    assert result.sources[0].identity == "doc-1"
    assert result.sources[0].content.endswith("[truncated]")
    assert result.tokens <= 180
    assert source.content == "á" * 300


def test_oversized_mandatory_question_fails_closed():
    def huge(history, sources):
        return [SystemMessage(content="rules"), HumanMessage(content="q" * 200)]

    with pytest.raises(budget.TokenBudgetError):
        asyncio.run(budget.fit_prompt(huge, [], [], Counter(), limits()))


def test_final_system_instructions_are_never_truncated():
    def huge_system(history, sources):
        return [SystemMessage(content="s" * 40), HumanMessage(content="question")]

    with pytest.raises(budget.TokenBudgetError):
        asyncio.run(budget.fit_prompt(huge_system, [], [], Counter(), limits()))


def test_short_prompt_is_unchanged_and_boundary_is_inclusive():
    original = render([], [])
    size = len("\n".join(m.content for m in original).encode())
    result = asyncio.run(budget.fit_prompt(render, [], [], Counter(), limits(input=size)))
    assert result.messages == original
    assert result.tokens == size


def test_counting_failure_never_returns_unchecked_prompt():
    class Broken(Counter):
        async def count(self, text):
            raise TimeoutError("provider unavailable")

    with pytest.raises(budget.TokenBudgetError):
        asyncio.run(budget.fit_prompt(render, [], [], Broken(), limits()))


def test_render_keeps_code_and_final_instructions_and_syncs_citations():
    from app.services import chat_service, rag_service

    low = rag_service.ScoredChunk("low " * 60, 0.1, {"document_id": "low"})
    high = rag_service.ScoredChunk("high evidence", 0.9, {"document_id": "high"})
    original = chat_service._format_messages(
        "answer-course-prompt",
        context=chat_service._course_context([low, high])
        + "\n\n### Student Code / Error Trace:\n```\nprint('keep')\n```",
        question="Explain this code",
        history="",
    )
    original[0] = SystemMessage(content="final language and tutoring rules")
    render_prompt, sources = chat_service._budget_renderer(original, [low, high], [])
    chosen = [s for s in sources if s.identity[0] == "document" and s.identity[1] is high]
    messages = render_prompt([], chosen)
    assert messages[0].content == original[0].content
    assert "print('keep')" in messages[1].content
    assert "[1]" in messages[1].content
    assert "[2]" not in messages[1].content
    assert "low " not in messages[1].content


def test_gateway_enforces_output_limit_and_rechecks_fallback(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services import gemini_key_service
    from app.services.llm import gateway

    seen = []
    counts = []

    class Model:
        async def astream(self, messages):
            yield SimpleNamespace(content="answer")

    def factory(**kwargs):
        seen.append(kwargs)
        return Model()

    async def counter(db, model=None, **kwargs):
        counts.append(model)
        return SimpleNamespace(
            input_limit=100,
            output_limit=50,
            count=Counter().count,
            client=SimpleNamespace(aclose=close),
        )

    async def close():
        pass

    monkeypatch.setattr(budget, "open_counter", counter)
    monkeypatch.setattr(gateway, "get_llm_model", factory)
    monkeypatch.setattr(gateway, "_candidate_models", lambda *args: ["primary", "fallback"])
    monkeypatch.setattr(
        gateway,
        "_select_key",
        lambda db, model, excluded: (
            None
            if model == "primary"
            else gemini_key_service.ResolvedGeminiKey(api_key="fake", key_id=None, key_name="test")
        ),
    )
    monkeypatch.setattr(gateway, "_record_success", lambda *args: None)
    monkeypatch.setattr(gateway, "_auto_switch_enabled", lambda *args: False)
    monkeypatch.setattr(budget.settings, "chat_token_safety_margin", 1)

    async def collect():
        return [
            x
            async for x in gateway.astream_chat(
                MagicMock(), render([], []), model="primary", max_output_tokens=20
            )
        ]

    assert asyncio.run(collect()) == ["answer"]
    assert counts == ["primary", "fallback"]
    assert seen[0]["max_output_tokens"] == 20


def test_history_blocks_keep_complete_pairs_even_with_student_marker():
    from app.services import chat_context_service

    exchange = chat_context_service.ConversationExchange(
        user="question\n\nStudent: quoted text", assistant="answer [9]"
    )
    blocks = chat_context_service.answer_history_blocks([exchange])
    assert len(blocks) == 1
    assert "Student: quoted text" in blocks[0]
    assert blocks[0].endswith("Assistant: answer")
    assert chat_context_service.answer_history_blocks([exchange], max_chars=10) == []


def test_counter_caches_exact_text_and_caps_provider_calls():
    from types import SimpleNamespace

    texts = []

    async def count_tokens(**kwargs):
        texts.append(kwargs["contents"])
        assert "config" not in kwargs
        return SimpleNamespace(total_tokens=3)

    counter = budget.GeminiTokenCounter(
        SimpleNamespace(models=SimpleNamespace(count_tokens=count_tokens)), "test", 10000, 1000
    )

    async def run():
        assert await counter.count("rules\nquestion") == 3
        assert await counter.count("rules\nquestion") == 3
        for i in range(7):
            await counter.count(str(i))
        with pytest.raises(budget.TokenBudgetError):
            await counter.count("ninth")

    asyncio.run(run())
    assert len(texts) == 8


def test_counter_timeout_does_not_fall_back_to_estimation(monkeypatch):
    from types import SimpleNamespace

    async def slow(**kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(budget.settings, "chat_token_count_timeout_seconds", 0.001)
    counter = budget.GeminiTokenCounter(
        SimpleNamespace(models=SimpleNamespace(count_tokens=slow)), "test", 10000, 1000
    )
    with pytest.raises(budget.TokenBudgetError):
        asyncio.run(budget.fit_prompt(render, [], [], counter, limits()))


def test_budget_settings_reject_invalid_section_caps():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="section token caps"):
        Settings(_env_file=None, CHAT_INPUT_MAX_TOKENS=10)


def test_fallback_with_small_context_never_opens_stream(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.llm import gateway

    async def close():
        pass

    async def small_counter(db, model=None, **kwargs):
        return SimpleNamespace(
            input_limit=10,
            output_limit=50,
            count=Counter().count,
            client=SimpleNamespace(aclose=close),
        )

    monkeypatch.setattr(budget, "open_counter", small_counter)
    monkeypatch.setattr(gateway, "_candidate_models", lambda *args: ["small"])
    opener = MagicMock()
    monkeypatch.setattr(gateway, "_open_stream", opener)

    async def collect():
        return [
            x
            async for x in gateway.astream_chat(
                MagicMock(), render([], []), model="small", max_output_tokens=20
            )
        ]

    with pytest.raises(budget.TokenBudgetError):
        asyncio.run(collect())
    opener.assert_not_called()


@pytest.mark.parametrize(
    "status,message",
    [(401, "revoked"), (400, "API_KEY_INVALID: API key not valid"), (429, "quota exhausted")],
)
def test_counting_rotates_failed_key_without_resetting_allowance(monkeypatch, status, message):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services import gemini_key_service

    failed, selected = [], []

    async def close():
        pass

    class BadKey(Exception):
        code = status

    async def fail(**kwargs):
        raise BadKey(message)

    async def success(**kwargs):
        return SimpleNamespace(total_tokens=7)

    def factory(**kwargs):
        selected.append(kwargs["api_key"])
        method = fail if kwargs["api_key"] == "bad" else success
        return SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(count_tokens=method), aclose=close)
        )

    keys = [
        gemini_key_service.ResolvedGeminiKey(
            api_key=name, key_id=name, key_name=name, key=SimpleNamespace(id=name)
        )
        for name in ("bad", "good")
    ]
    monkeypatch.setattr(budget.genai, "Client", factory)
    monkeypatch.setattr(
        gemini_key_service,
        "resolve_key",
        lambda db, model, exclude_ids=None: next(
            (key for key in keys if key.key_id not in (exclude_ids or set())), None
        ),
    )
    monkeypatch.setattr(
        gemini_key_service, "mark_key_failure", lambda db, key, exc: failed.append(key.id)
    )
    monkeypatch.setattr(gemini_key_service, "get_auto_switch", lambda db: True)
    monkeypatch.setitem(budget._model_limits, "test", (10000, 1000))

    async def run():
        counter = await budget.open_counter(MagicMock(), "test")
        assert await counter.count("hello") == 7
        assert counter.calls == 2
        await counter.client.aclose()

    asyncio.run(run())
    assert selected == ["bad", "good"]
    assert failed == ["bad"]


def test_fallback_cannot_reset_exhausted_count_allowance():
    from types import SimpleNamespace

    async def count_tokens(**kwargs):
        return SimpleNamespace(total_tokens=1)

    client = SimpleNamespace(models=SimpleNamespace(count_tokens=count_tokens))
    allowance = budget.CountingAllowance()

    async def run():
        first = budget.GeminiTokenCounter(client, "primary", 10000, 1000, allowance=allowance)
        for i in range(8):
            await first.count(str(i))
        fallback = budget.GeminiTokenCounter(client, "fallback", 10000, 1000, allowance=allowance)
        with pytest.raises(budget.TokenBudgetError):
            await fallback.count("final prompt")
        assert first.calls == fallback.calls == 8

    asyncio.run(run())


@pytest.mark.parametrize("counter_fails", [False, True])
def test_twenty_turn_stream_checks_final_prompt_and_reports_count_failure(
    monkeypatch, counter_fails
):
    import json
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services import chat_context_service, chat_service, decision_service, rag_service

    captured = []

    class Model:
        def bind(self, **kwargs):
            assert kwargs["max_output_tokens"] == budget.settings.chat_answer_max_tokens
            return self

        async def astream(self, messages):
            captured.extend(messages)
            assert (
                len(budget.prompt_text(messages).encode()) <= budget.settings.chat_input_max_tokens
            )
            yield SimpleNamespace(content="A loop repeats instructions [1].")

    async def count(text):
        if counter_fails:
            raise TimeoutError("provider down")
        return (len(text.encode()) + 3) // 4

    async def close():
        pass

    async def counter(db, model=None, **kwargs):
        return SimpleNamespace(
            model="fake",
            input_limit=100000,
            output_limit=10000,
            count=count,
            client=SimpleNamespace(aclose=close),
        )

    async def scope(**kwargs):
        return decision_service.ScopeDecision(verdict="core", confidence=1.0)

    async def rewrite(history, question, **kwargs):
        return question

    async def suggestions(**kwargs):
        return []

    chunks = (
        rag_service.ScoredChunk(
            "low relevance " * 100, 0.81, {"document_id": "low", "title": "Low"}
        ),
        rag_service.ScoredChunk(
            "A loop repeats instructions.",
            0.99,
            {"document_id": "high", "title": "High", "page": 2},
        ),
    )
    decision = rag_service.RetrievalDecision(
        question="Explain loops",
        class_id="class-a",
        threshold=0.8,
        top_score=0.99,
        source=rag_service.SOURCE_CURRICULUM,
        chunks=chunks,
    )
    monkeypatch.setattr(budget, "open_counter", counter)
    monkeypatch.setattr(chat_service, "_resolve_scope_decision", scope)
    monkeypatch.setattr(chat_context_service, "condense_question", rewrite)
    monkeypatch.setattr(chat_service.course_service, "get_class", lambda *args: None)
    monkeypatch.setattr(chat_service, "_format_syllabus_roadmap", lambda *args: ("", None))
    monkeypatch.setattr(
        chat_service.chat_retrieval_service, "retrieve_for_chat", lambda *args, **kwargs: decision
    )
    monkeypatch.setattr(chat_service.suggestion_service, "generate_followup_questions", suggestions)
    monkeypatch.setattr(
        chat_service.suggestion_service, "build_fallback_followups", lambda **kwargs: []
    )
    monkeypatch.setattr(budget.settings, "chat_history_max_tokens", 200)
    monkeypatch.setattr(budget.settings, "chat_documents_max_tokens", 100)
    monkeypatch.setattr(budget.settings, "chat_context_max_chars", 30000)
    history = [
        chat_context_service.ConversationExchange(
            user=f"old question {i}", assistant="Previous explanation " * 10
        )
        for i in range(20)
    ]

    async def collect():
        return [
            event
            async for event in chat_service.stream_chat(
                db=MagicMock(),
                message="Explain how a loop repeats instructions",
                class_id="class-a",
                history=history,
                model=Model(),
                timeout_seconds=2,
            )
        ]

    raw = asyncio.run(collect())
    events = [
        (
            item.splitlines()[0].removeprefix("event: "),
            json.loads(item.splitlines()[1].removeprefix("data: ")),
        )
        for item in raw
    ]
    if counter_fails:
        assert not captured
        assert events[-1][0] == "error"
        assert all(event != "done" for event, _ in events)
    else:
        assert events[-1][0] == "done"
        assert "old question 0" not in captured[1].content
        assert "low relevance" not in captured[1].content
        citations = [value for event, value in events if event == "citation"]
        assert citations[0]["document_id"] == "high"
        assert citations[0]["index"] == 1
        assert len(history) == 20


def test_truncated_table_source_does_not_reinsert_discarded_header():
    from app.services import chat_service, rag_service

    header = "Column One | Column Two | Column Three"
    chunk = rag_service.ScoredChunk(
        header + "\nrow contents",
        0.9,
        {"document_id": "table", "title": "Table", "table_header": header},
    )
    messages = chat_service._format_messages(
        "answer-course-prompt",
        context=chat_service._course_context([chunk]),
        question="Explain the table",
    )
    render_prompt, sources = chat_service._budget_renderer(messages, [chunk], [])
    selected = [replace(sources[0], content="Column [truncated]")]
    prompt = render_prompt([], selected)
    assert header not in prompt[1].content
    assert "Column [truncated]" in prompt[1].content
