"""Strict course-source evidence contract and deterministic evaluator.

Foundation-only slice. This module does not touch the chat router, SSE stream,
database schema, retrieval stack, or web search. A future slice can map
``chat_retrieval_service`` chunks into :class:`StrictSource` values, call
:func:`generate_strict_sources_answer`, and use the validated result to decide
whether to answer, ask for web consent for missing intents, or ask for consent
for the whole question.

The model call performs intent decomposition and evidence mapping in one step.
Each intent must also carry an exact segment of the original question. The
server verifies that segments are ordered exact substrings and that together
they cover all substantive question text. A model that omits a subquestion
therefore cannot produce a ``full`` result. When a single supported intent is
followed by a completeness audit that finds multiple ordered segments, one
bounded recovery call regenerates intents aligned to those exact segments; the
recovered payload still passes the same coverage, source-ID, support, and
conflict validation. If recovery fails, the turn fails closed. A model-declared
``supported`` status is still a model judgement; the server does not treat a
valid source ID, a retrieval score, valid coverage, or the model status enum as
proof of entailment. Any invalid ID, omitted or malformed coverage, malformed
payload, timeout, or provider failure raises before a result or draft is
returned.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.prompt_manager import get_prompt_manager
from app.services import rag_service
from app.services.llm import gateway

logger = logging.getLogger(__name__)

EvidenceStatus = Literal["supported", "unsupported", "conflicting"]
ResultStatus = Literal["full", "partial", "none"]
ResultReason = Literal["no_sources", "no_supported_evidence", "all_conflicting"]

STRICT_SOURCES_PROMPT = "strict-sources-prompt"
STRICT_SOURCES_COMPLETENESS_PROMPT = "strict-sources-completeness-prompt"
STRICT_SOURCES_RECOVERY_PROMPT = "strict-sources-recovery-prompt"


class StrictSourcesError(RuntimeError):
    """Base error for a strict-source turn that must not emit an answer."""


class StrictSourcesValidationError(StrictSourcesError):
    """The model payload or its source references violate the contract."""


class StrictSourcesModelError(StrictSourcesError):
    """The model call failed or timed out before a validated result existed."""


@dataclass(frozen=True)
class StrictSource:
    """One class-owned source chunk supplied to the evidence evaluator."""

    source_id: str
    content: str
    title: str = ""
    document_id: str | None = None
    page: int | None = None


class _ModelIntent(BaseModel):
    """One intent and its evidence mapping as proposed by the model."""

    intent_id: str
    question: str
    question_segment: str = Field(..., min_length=1)
    status: EvidenceStatus
    claim: str = ""
    explanation: str = ""
    source_ids: list[str] = Field(default_factory=list)
    limitation: str = ""
    conflict_note: str = ""


class StrictSourcesModelOutput(BaseModel):
    """The single model response accepted by the strict-source contract."""

    intents: list[_ModelIntent] = Field(..., min_length=1)


class _CompletenessSegment(BaseModel):
    """One exact question segment returned by the second-pass audit."""

    segment_id: str
    question_segment: str = Field(..., min_length=1)


class CompletenessAudit(BaseModel):
    """Second-pass decomposition used when a single intent claims full coverage."""

    segments: list[_CompletenessSegment] = Field(..., min_length=1)


class ValidatedIntent(BaseModel):
    """A server-validated intent; only supported intents carry a claim."""

    intent_id: str
    question: str
    question_segment: str
    status: EvidenceStatus
    claim: str | None = None
    explanation: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    limitation: str | None = None
    conflict_note: str | None = None


class StrictSourcesResult(BaseModel):
    """Validated evidence outcome for one student question.

    ``answer`` is a deterministic draft composed only from supported
    explanations (falling back to the short claim when no explanation is given).
    It is ``None`` when no intent is supported, so a caller cannot accidentally
    stream an unvalidated model draft. ``reason`` distinguishes a missing-source
    turn from a genuine no-evidence turn and an all-conflicting turn.
    """

    question: str
    status: ResultStatus
    reason: ResultReason | None = None
    answer: str | None = None
    intents: list[ValidatedIntent] = Field(default_factory=list)
    supported_intent_ids: list[str] = Field(default_factory=list)
    unsupported_intent_ids: list[str] = Field(default_factory=list)
    conflicting_intent_ids: list[str] = Field(default_factory=list)
    source_ids_used: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


ModelInvoker = Callable[[Sequence[Any]], Awaitable[str]]


def sources_from_chunks(
    chunks: Sequence[rag_service.ScoredChunk],
    *,
    prefix: str = "S",
) -> tuple[StrictSource, ...]:
    """Map reranked class chunks to stable source IDs without using their scores."""

    return tuple(
        StrictSource(
            source_id=f"{prefix}{index}",
            content=chunk.content,
            title=chunk.title,
            document_id=chunk.document_id or None,
            page=chunk.page,
        )
        for index, chunk in enumerate(chunks, start=1)
    )


def _sources_json(sources: Sequence[StrictSource]) -> str:
    return json.dumps(
        [
            {
                "source_id": source.source_id,
                "title": source.title,
                "content": source.content,
                "document_id": source.document_id,
                "page": source.page,
            }
            for source in sources
        ],
        ensure_ascii=False,
        indent=2,
    )


def build_strict_sources_messages(
    question: str,
    sources: Sequence[StrictSource],
) -> list[SystemMessage | HumanMessage]:
    """Build the strict-source answer prompt with source text isolated as untrusted data."""

    cleaned_question = (question or "").strip()
    if not cleaned_question:
        raise ValueError("Question must not be empty.")
    normalised = _normalise_sources(sources)
    if not normalised:
        raise ValueError("At least one source is required to build the strict-source prompt.")

    prompt = get_prompt_manager().format(
        STRICT_SOURCES_PROMPT,
        question=cleaned_question,
        sources_json=_sources_json(normalised),
    )
    return [
        SystemMessage(content=str(prompt["system-prompt"])),
        HumanMessage(content=str(prompt["user-prompt"])),
    ]


def build_strict_sources_recovery_messages(
    question: str,
    sources: Sequence[StrictSource],
    audit: CompletenessAudit,
) -> list[SystemMessage | HumanMessage]:
    """Build the bounded recovery prompt from the audit's exact ordered segments."""

    cleaned_question = (question or "").strip()
    if not cleaned_question:
        raise ValueError("Question must not be empty.")
    normalised = _normalise_sources(sources)
    if not normalised:
        raise ValueError("At least one source is required to build the recovery prompt.")
    if not audit.segments:
        raise ValueError("The completeness audit must contain at least one segment.")

    segments_json = json.dumps(
        [
            {
                "segment_id": segment.segment_id,
                "question_segment": segment.question_segment,
            }
            for segment in audit.segments
        ],
        ensure_ascii=False,
        indent=2,
    )
    prompt = get_prompt_manager().format(
        STRICT_SOURCES_RECOVERY_PROMPT,
        question=cleaned_question,
        segments_json=segments_json,
        sources_json=_sources_json(normalised),
    )
    return [
        SystemMessage(content=str(prompt["system-prompt"])),
        HumanMessage(content=str(prompt["user-prompt"])),
    ]


def build_completeness_messages(question: str) -> list[SystemMessage | HumanMessage]:
    """Build the second-pass question-decomposition prompt (no sources, no answer)."""

    cleaned_question = (question or "").strip()
    if not cleaned_question:
        raise ValueError("Question must not be empty.")
    prompt = get_prompt_manager().format(
        STRICT_SOURCES_COMPLETENESS_PROMPT,
        question=cleaned_question,
    )
    return [
        SystemMessage(content=str(prompt["system-prompt"])),
        HumanMessage(content=str(prompt["user-prompt"])),
    ]


def parse_completeness_output(raw: str) -> CompletenessAudit:
    """Parse and schema-validate the second-pass completeness audit."""

    cleaned = str(raw or "").strip()
    if not cleaned:
        raise StrictSourcesValidationError("Completeness audit output is empty.")

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise StrictSourcesValidationError(
            "Completeness audit output is not a JSON object."
        )
    cleaned = cleaned[start : end + 1]

    try:
        payload = json.loads(cleaned)
    except (TypeError, ValueError) as exc:
        raise StrictSourcesValidationError(
            "Completeness audit output is not valid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise StrictSourcesValidationError(
            "Completeness audit output is not a JSON object."
        )

    try:
        return CompletenessAudit.model_validate(payload)
    except ValidationError as exc:
        raise StrictSourcesValidationError(
            "Completeness audit output does not match the required JSON schema."
        ) from exc


def parse_strict_sources_output(raw: str) -> StrictSourcesModelOutput:
    """Parse and schema-validate one model response; never fail open."""

    cleaned = str(raw or "").strip()
    if not cleaned:
        raise StrictSourcesValidationError("Strict source model output is empty.")

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise StrictSourcesValidationError(
            "Strict source model output is not a JSON object."
        )
    cleaned = cleaned[start : end + 1]

    try:
        payload = json.loads(cleaned)
    except (TypeError, ValueError) as exc:
        raise StrictSourcesValidationError(
            "Strict source model output is not valid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise StrictSourcesValidationError(
            "Strict source model output is not a JSON object."
        )

    try:
        return StrictSourcesModelOutput.model_validate(payload)
    except ValidationError as exc:
        raise StrictSourcesValidationError(
            "Strict source model output does not match the required JSON schema."
        ) from exc


def evaluate_strict_sources(
    question: str,
    sources: Sequence[StrictSource],
    model_output: StrictSourcesModelOutput | Mapping[str, Any] | str,
    *,
    completeness_audit: CompletenessAudit | None = None,
) -> StrictSourcesResult:
    """Validate evidence and compose a draft from supported claims only.

    The retrieval score is deliberately absent from this contract: a high score
    does not promote unrelated text to evidence. The model's ``status`` field is
    validated structurally, not treated as proof that the claim is entailed.
    Coverage is validated separately: every substantive part of the original
    question must be represented by an ordered, exact question segment. A
    single-intent ``full`` result additionally requires a second-pass
    completeness audit that also finds exactly one segment; without that audit
    the evaluator refuses to claim full coverage.
    """

    cleaned_question = (question or "").strip()
    if not cleaned_question:
        raise ValueError("Question must not be empty.")
    normalised = _normalise_sources(sources)
    if not normalised:
        return _empty_result(cleaned_question, "no_sources")

    parsed = _coerce_model_output(model_output)
    _validate_question_coverage(cleaned_question, parsed.intents)
    allowed_ids = {source.source_id for source in normalised}
    seen_intents: set[str] = set()
    intents: list[ValidatedIntent] = []
    supported: list[ValidatedIntent] = []
    unsupported: list[ValidatedIntent] = []
    conflicting: list[ValidatedIntent] = []
    limitations: list[str] = []
    source_ids_used: list[str] = []

    for raw_intent in parsed.intents:
        intent_id = raw_intent.intent_id.strip()
        intent_question = raw_intent.question.strip()
        if not intent_id or not intent_question:
            raise StrictSourcesValidationError(
                "Every strict-source intent needs a non-empty intent_id and question."
            )
        if intent_id in seen_intents:
            raise StrictSourcesValidationError(
                f"Duplicate strict-source intent_id '{intent_id}'."
            )
        seen_intents.add(intent_id)
        source_ids = _validate_source_ids(raw_intent.source_ids, allowed_ids)

        if raw_intent.status == "supported":
            claim = raw_intent.claim.strip()
            if not claim:
                raise StrictSourcesValidationError(
                    f"Supported intent '{intent_id}' must include a supported claim."
                )
            if not source_ids:
                raise StrictSourcesValidationError(
                    f"Supported intent '{intent_id}' must cite at least one source."
                )
            explanation = raw_intent.explanation.strip() or claim
            intent = ValidatedIntent(
                intent_id=intent_id,
                question=intent_question,
                question_segment=raw_intent.question_segment,
                status="supported",
                claim=claim,
                explanation=explanation,
                source_ids=source_ids,
            )
            supported.append(intent)
            for source_id in source_ids:
                if source_id not in source_ids_used:
                    source_ids_used.append(source_id)
        elif raw_intent.status == "unsupported":
            limitation = raw_intent.limitation.strip() or (
                "No course material supported this part of the question."
            )
            intent = ValidatedIntent(
                intent_id=intent_id,
                question=intent_question,
                question_segment=raw_intent.question_segment,
                status="unsupported",
                source_ids=source_ids,
                limitation=limitation,
            )
            unsupported.append(intent)
            limitations.append(f"{intent_question}: {limitation}")
        else:
            if not source_ids:
                raise StrictSourcesValidationError(
                    f"Conflicting intent '{intent_id}' must cite the conflicting sources."
                )
            conflict_note = raw_intent.conflict_note.strip() or (
                "Course sources conflict; no answer was selected."
            )
            intent = ValidatedIntent(
                intent_id=intent_id,
                question=intent_question,
                question_segment=raw_intent.question_segment,
                status="conflicting",
                source_ids=source_ids,
                conflict_note=conflict_note,
            )
            conflicting.append(intent)
            limitations.append(f"{intent_question}: {conflict_note}")

        intents.append(intent)

    if len(supported) == len(intents):
        status: ResultStatus = "full"
        reason: ResultReason | None = None
    elif supported:
        status = "partial"
        reason = None
    else:
        status = "none"
        reason = "all_conflicting" if conflicting and not unsupported else "no_supported_evidence"

    if status == "full" and len(intents) == 1:
        if completeness_audit is None:
            raise StrictSourcesValidationError(
                "A single-intent full result requires a second-pass completeness audit."
            )
        _validate_completeness_audit(cleaned_question, completeness_audit)
        if len(completeness_audit.segments) != 1:
            raise StrictSourcesValidationError(
                "Second-pass completeness audit found multiple semantic segments; "
                "refusing to claim full coverage."
            )

    return StrictSourcesResult(
        question=cleaned_question,
        status=status,
        reason=reason,
        answer=_compose_answer(supported),
        intents=intents,
        supported_intent_ids=[intent.intent_id for intent in supported],
        unsupported_intent_ids=[intent.intent_id for intent in unsupported],
        conflicting_intent_ids=[intent.intent_id for intent in conflicting],
        source_ids_used=source_ids_used,
        limitations=limitations,
    )


async def generate_strict_sources_answer(
    *,
    question: str,
    sources: Sequence[StrictSource],
    db: Session | None = None,
    model_invoker: ModelInvoker | None = None,
    timeout_seconds: float | None = None,
    messages_builder: Callable[[str, Sequence[StrictSource]], list[Any]] | None = None,
) -> StrictSourcesResult:
    """Run up to three model calls and return only a validated strict-source result.

    The first call decomposes intents and maps evidence. A single-intent full
    result requires a second-pass completeness audit on the same key-pool
    gateway/model. If that audit finds multiple ordered semantic segments, one
    bounded recovery call regenerates intents aligned to those exact segments;
    the recovered payload is still validated for coverage, source IDs, support,
    and conflicts. Other outcomes use one call. Tests and future callers may
    inject ``model_invoker``. Without sources, the model is not called and the
    result is ``none`` with ``reason="no_sources"``.
    """

    cleaned_question = (question or "").strip()
    if not cleaned_question:
        raise ValueError("Question must not be empty.")
    normalised = _normalise_sources(sources)
    if not normalised:
        return _empty_result(cleaned_question, "no_sources")

    builder = messages_builder or build_strict_sources_messages
    messages = builder(cleaned_question, normalised)
    raw_output = await _invoke_model(
        messages=messages,
        db=db,
        model_invoker=model_invoker,
        timeout_seconds=timeout_seconds,
    )
    parsed = parse_strict_sources_output(raw_output)
    _validate_question_coverage(cleaned_question, parsed.intents)

    completeness_audit: CompletenessAudit | None = None
    if (
        len(parsed.intents) == 1
        and parsed.intents[0].status == "supported"
        and parsed.intents[0].claim.strip()
        and parsed.intents[0].source_ids
    ):
        _validate_source_ids(
            parsed.intents[0].source_ids,
            {source.source_id for source in normalised},
        )
        audit = await _audit_question_completeness(
            question=cleaned_question,
            db=db,
            model_invoker=model_invoker,
            timeout_seconds=timeout_seconds,
        )
        _validate_completeness_audit(cleaned_question, audit)
        if len(audit.segments) == 1:
            completeness_audit = audit
        else:
            parsed = await _recover_from_audit(
                question=cleaned_question,
                sources=normalised,
                audit=audit,
                db=db,
                model_invoker=model_invoker,
                timeout_seconds=timeout_seconds,
            )

    return evaluate_strict_sources(
        cleaned_question,
        normalised,
        parsed,
        completeness_audit=completeness_audit,
    )


async def _audit_question_completeness(
    *,
    question: str,
    db: Session | None,
    model_invoker: ModelInvoker | None,
    timeout_seconds: float | None,
) -> CompletenessAudit:
    """Run one second-pass decomposition call; never fall back to full."""

    messages = build_completeness_messages(question)
    raw_output = await _invoke_model(
        messages=messages,
        db=db,
        model_invoker=model_invoker,
        timeout_seconds=timeout_seconds,
    )
    return parse_completeness_output(raw_output)


async def _recover_from_audit(
    *,
    question: str,
    sources: Sequence[StrictSource],
    audit: CompletenessAudit,
    db: Session | None,
    model_invoker: ModelInvoker | None,
    timeout_seconds: float | None,
) -> StrictSourcesModelOutput:
    """Run exactly one bounded recovery call aligned to the audit segments."""

    messages = build_strict_sources_recovery_messages(question, sources, audit)
    raw_output = await _invoke_model(
        messages=messages,
        db=db,
        model_invoker=model_invoker,
        timeout_seconds=timeout_seconds,
    )
    parsed = parse_strict_sources_output(raw_output)
    _validate_recovery_segments(question, parsed.intents, audit)
    return parsed


def _empty_result(question: str, reason: ResultReason) -> StrictSourcesResult:
    return StrictSourcesResult(
        question=question,
        status="none",
        reason=reason,
        answer=None,
    )


def _normalise_sources(sources: Sequence[StrictSource]) -> tuple[StrictSource, ...]:
    if not sources:
        return ()

    normalised: list[StrictSource] = []
    seen_ids: set[str] = set()
    for source in sources:
        source_id = source.source_id.strip()
        if not source_id:
            raise ValueError("Every source needs a non-empty source_id.")
        if not source.content.strip():
            raise ValueError(f"Source '{source_id}' has no content.")
        if source_id in seen_ids:
            raise ValueError(f"Duplicate source_id '{source_id}'.")
        seen_ids.add(source_id)
        normalised.append(
            StrictSource(
                source_id=source_id,
                content=source.content,
                title=source.title,
                document_id=source.document_id,
                page=source.page,
            )
        )
    return tuple(normalised)


def _validate_question_coverage(
    question: str,
    intents: Sequence[_ModelIntent],
) -> None:
    """Require ordered exact intent segments that cover every substantive character."""

    _validate_ordered_segments(
        question,
        [(intent.intent_id, intent.question_segment) for intent in intents],
        label="Intent",
    )


def _validate_completeness_audit(question: str, audit: CompletenessAudit) -> None:
    """Require the second-pass audit's segments to cover the whole question."""

    _validate_ordered_segments(
        question,
        [(segment.segment_id, segment.question_segment) for segment in audit.segments],
        label="Audit segment",
    )


def _validate_recovery_segments(
    question: str,
    intents: Sequence[_ModelIntent],
    audit: CompletenessAudit,
) -> None:
    """Require one recovered intent per audit segment, in the audit's exact order."""

    if len(intents) != len(audit.segments):
        raise StrictSourcesValidationError(
            "Recovery must return exactly one intent per audit segment."
        )
    for intent, segment in zip(intents, audit.segments, strict=True):
        if intent.question_segment.strip() != segment.question_segment.strip():
            raise StrictSourcesValidationError(
                "Recovery intent segments must match the audit segments in order."
            )
    _validate_question_coverage(question, intents)


def _validate_ordered_segments(
    question: str,
    labeled_segments: Sequence[tuple[str, str]],
    *,
    label: str,
) -> None:
    """Validate ordered exact segments and substantive-text coverage.

    Whitespace, punctuation and symbols are ignored for the coverage check, but
    each non-empty segment must still be an exact substring of the original
    question. The segments must appear in order and must not overlap. This can
    detect an omitted subquestion, but it cannot prove that the model's semantic
    decomposition is correct; the prompts still carry that responsibility.
    """

    covered: set[int] = set()
    cursor = 0
    for segment_id, segment in labeled_segments:
        if not segment or not segment.strip():
            raise StrictSourcesValidationError(
                f"{label} '{segment_id}' has an empty question_segment."
            )
        if not any(char.isalnum() for char in segment):
            raise StrictSourcesValidationError(
                f"{label} '{segment_id}' question_segment has no substantive text."
            )
        start = question.find(segment, cursor)
        if start == -1:
            raise StrictSourcesValidationError(
                f"{label} '{segment_id}' question_segment is not an ordered "
                "exact substring of the original question."
            )
        end = start + len(segment)
        covered.update(range(start, end))
        cursor = end

    for index, char in enumerate(question):
        if char.isalnum() and index not in covered:
            raise StrictSourcesValidationError(
                "The returned segments do not cover all substantive text in the "
                "original question."
            )


def _coerce_model_output(
    model_output: StrictSourcesModelOutput | Mapping[str, Any] | str,
) -> StrictSourcesModelOutput:
    if isinstance(model_output, StrictSourcesModelOutput):
        return model_output
    if isinstance(model_output, str):
        return parse_strict_sources_output(model_output)
    if isinstance(model_output, Mapping):
        try:
            return StrictSourcesModelOutput.model_validate(model_output)
        except ValidationError as exc:
            raise StrictSourcesValidationError(
                "Strict source model output does not match the required JSON schema."
            ) from exc
    raise StrictSourcesValidationError(
        "Strict source model output must be a JSON object or StrictSourcesModelOutput."
    )


def _validate_source_ids(raw_ids: Sequence[str], allowed_ids: set[str]) -> list[str]:
    source_ids: list[str] = []
    for raw_id in raw_ids:
        source_id = str(raw_id or "").strip()
        if not source_id:
            raise StrictSourcesValidationError("Source IDs must not be empty.")
        if source_id not in allowed_ids:
            raise StrictSourcesValidationError(
                f"Source ID '{source_id}' is not part of the input chunks."
            )
        if source_id not in source_ids:
            source_ids.append(source_id)
    return source_ids


def _compose_answer(supported: Sequence[ValidatedIntent]) -> str | None:
    paragraphs: list[str] = []
    for intent in supported:
        text = (intent.explanation or intent.claim or "").strip()
        if not text:
            continue
        markers = " ".join(f"[{source_id}]" for source_id in intent.source_ids)
        paragraphs.append(f"{text} {markers}".strip())
    return "\n\n".join(paragraphs) if paragraphs else None


async def _invoke_model(
    *,
    messages: Sequence[Any],
    db: Session | None,
    model_invoker: ModelInvoker | None,
    timeout_seconds: float | None,
) -> str:
    async def call() -> str:
        if model_invoker is not None:
            return await model_invoker(messages)
        if timeout_seconds is None:
            return await gateway.ainvoke_chat(db, messages)
        return await gateway.ainvoke_chat(db, messages, timeout=timeout_seconds)

    try:
        if timeout_seconds is None:
            return await call()
        return await asyncio.wait_for(call(), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise StrictSourcesModelError("Strict source model timed out.") from exc
    except StrictSourcesError:
        raise
    except Exception as exc:
        logger.warning("Strict source model call failed: %s", type(exc).__name__)
        raise StrictSourcesModelError("Strict source model failed.") from exc
