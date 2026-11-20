"""Strict-source chat orchestration: course evidence first, web only after consent.

This service is the new ``POST /api/chat`` path. It reuses the existing class
retrieval/reranking stack and the strict-source evaluator. It never calls the
Internet search agent. Partial and none outcomes persist a user-bound consent
offer, and the separate consent endpoint performs web work only after an
explicit accept.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config.config import settings
from app.schemas.chat import WebConsentResult
from app.schemas.history import ChatCitation
from app.services import (
    chat_context_service,
    chat_retrieval_service,
    content_gap_telemetry,
    course_service,
    decision_service,
    document_answer_service,
    document_service,
    history_service,
    quick_response_service,
    rag_service,
    strict_sources_service,
    strict_web_service,
    suggestion_service,
    web_consent_service,
)
from app.services.chat_context_service import ConversationExchange
from app.services.chat_service import (
    _HOMEWORK_PATTERNS,
    GENERATION_ERROR_MESSAGE,
    SUGGESTION_PREFETCH_GRACE_SECONDS,
    TIMEOUT_ERROR_MESSAGE,
    _format_syllabus_roadmap,
    _is_syllabus_relevant_question,
    _tag_pedagogy,
)
from app.services.llm import gateway

logger = logging.getLogger(__name__)

NO_COURSE_EVIDENCE_MESSAGE = (
    "I could not find enough evidence in this class's materials to answer that. "
    "You can accept a web search for the full question if you want me to look "
    "outside the course materials."
)
NO_CLASS_DOCUMENTS_MESSAGE = "Giáo viên chưa tải tài liệu nào cho khóa học này."
STRICT_GENERATION_ERROR_MESSAGE = (
    "The course-material answer could not be validated. Please try again."
)
WEB_CONSENT_ERROR_MESSAGE = (
    "The web answer could not be completed. Please try again."
)
WEB_CONSENT_TIMEOUT_MESSAGE = (
    "The web answer timed out. Please try again."
)


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _citation_dict(source: rag_service.Source) -> dict[str, Any]:
    d = asdict(source)
    pages = d.get("pages")
    page = d.get("page")
    page_label = d.get("page_label")
    if not pages or (page is not None and list(pages) == [page]):
        d.pop("pages", None)
    if not page_label or (page is not None and page_label == str(page)):
        d.pop("page_label", None)
    return d


def _persist_turn(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    class_id: uuid.UUID | str,
    message: str,
    answer: str,
    citations: Sequence[dict[str, Any]],
    trace: Sequence[str],
    suggested_questions: Sequence[str] | None = None,
    excluded_from_context: bool = False,
    thinking_ms: int | None = None,
    query_embedding: Sequence[float] | None = None,
    fallback_reason: str | None = None,
) -> tuple[Any, Any, Any] | None:
    if user_id is None or not answer.strip():
        return None
    try:
        return history_service.save_chat_turn(
            db=db,
            user_id=user_id,
            class_id=class_id,
            user_content=message,
            assistant_content=answer,
            session_id=session_id,
            used_web_search=False,
            citations=citations,
            suggested_questions=suggested_questions,
            trace=trace,
            excluded_from_context=excluded_from_context,
            thinking_ms=thinking_ms,
            query_embedding=list(query_embedding) if query_embedding else None,
            fallback_reason=fallback_reason,
            sync_content_gap=False,
        )
    except Exception:
        logger.exception("Failed to persist strict-source chat turn.")
        return None


def _schedule_content_gap_sync(
    *,
    message_id: str,
    class_id: str,
    student_id: str,
    embedding: Sequence[float] | None,
    fallback_reason: str | None,
) -> None:
    if not embedding:
        return
    content_gap_telemetry.schedule_capture(
        history_service.sync_content_gap_query,
        message_id=message_id,
        class_id=class_id,
        student_id=student_id,
        embedding=list(embedding),
        source="material",
        fallback_reason=fallback_reason,
        embedding_model_version=settings.embedding_model,
    )


def _schedule_content_gap_source_update(message_id: str) -> None:
    content_gap_telemetry.schedule_web_update(
        history_service.update_content_gap_source,
        message_id=message_id,
    )


async def wait_for_content_gap_tasks(timeout: float = 2.0) -> None:
    """Await in-flight best-effort telemetry (tests and graceful shutdown)."""

    await content_gap_telemetry.wait_for_tasks(timeout)


def _fallback_reason(
    result: strict_sources_service.StrictSourcesResult,
    decision: rag_service.RetrievalDecision,
) -> str | None:
    """Describe why the course lane needed the consent fallback.

    This is telemetry only: it reuses the retrieval decision and never changes
    a threshold, gate or the full/partial/none status.
    """

    if result.status == "full":
        return None
    if not decision.chunks:
        return "no_results"
    if decision.top_score is not None and decision.top_score < decision.threshold:
        return "similarity_below_threshold"
    return "insufficient_context"


def _source_citations(
    chunks: Sequence[rag_service.ScoredChunk],
    source_ids_used: Sequence[str],
) -> list[rag_service.Source]:
    used = {str(source_id) for source_id in source_ids_used}
    return [
        citation
        for citation in rag_service.curriculum_citations(chunks)
        if str(citation.index) in used
    ]


def _web_source_links(sources: Sequence[rag_service.Source]) -> list[rag_service.Source]:
    """Every valid search-result URL, independent of model citation markers.

    The web answer may omit ``[n]`` markers; the Web Sources panel and the
    persisted citations must still point at the URLs fetched during consent.
    """

    links: list[rag_service.Source] = []
    seen: set[str] = set()
    for source in sources:
        url = (source.url or "").strip()
        try:
            parsed = urlparse(url)
            _ = parsed.port  # force validation of a malformed port
        except ValueError:
            continue
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append(source)
    return links


def _conflict_intents(result: strict_sources_service.StrictSourcesResult):
    return [intent for intent in result.intents if intent.status == "conflicting"]


def _conflict_warning(result: strict_sources_service.StrictSourcesResult) -> str | None:
    conflicts = _conflict_intents(result)
    if not conflicts:
        return None
    lines = [
        "**Source conflict warning:** the course materials disagree, so I am not choosing a winner."
    ]
    for intent in conflicts:
        note = (intent.conflict_note or "The sources conflict; no answer was selected.").strip()
        markers = " ".join(f"[{source_id}]" for source_id in intent.source_ids)
        lines.append(f"- {intent.question}: {note} {markers}".strip())
    return "\n".join(lines)


def _conflict_source_ids(result: strict_sources_service.StrictSourcesResult) -> list[str]:
    source_ids: list[str] = []
    for intent in _conflict_intents(result):
        for source_id in intent.source_ids:
            if source_id not in source_ids:
                source_ids.append(source_id)
    return source_ids


def _answer_chunks(answer: str, size: int = 120) -> list[str]:
    if not answer:
        return []
    return [answer[index : index + size] for index in range(0, len(answer), size)]


async def stream_chat(
    *,
    db: Session,
    message: str,
    class_id: uuid.UUID | str,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    history: Sequence[ConversationExchange] | None = None,
    strict_model_invoker: strict_sources_service.ModelInvoker | None = None,
    timeout_seconds: float | None = None,
) -> AsyncIterator[str]:
    """Stream a validated course-only answer and, when needed, a consent offer.

    Answer tokens are emitted only after the strict-source evaluator has
    validated the evidence. The web search agent is never called here.
    """

    context_history = list(history or ())
    budget = timeout_seconds if timeout_seconds is not None else settings.chat_timeout_seconds
    started = time.monotonic()
    trace: list[str] = []
    is_hw = bool(_HOMEWORK_PATTERNS.search(message))

    try:
        if user_id is not None and session_id is not None:
            web_consent_service.expire_pending_offers(
                db,
                user_id=user_id,
                session_id=session_id,
            )

        quick_answer = quick_response_service.get_quick_response(message)
        if quick_answer:
            for part in quick_response_service.split_into_stream_chunks(quick_answer):
                yield _sse("token", {"text": part})
            trace.append(f"pedagogy:{_tag_pedagogy(message)}")
            saved = _persist_turn(
                db,
                user_id=user_id,
                session_id=session_id,
                class_id=class_id,
                message=message,
                answer=quick_answer,
                citations=[],
                trace=trace,
                thinking_ms=0,
                # A fixed greeting/thanks reply is not evidence for the course
                # lane and must not become a Content Gap material answer.
                excluded_from_context=True,
            )
            saved_session, user_msg, assistant_msg = saved or (None, None, None)
            yield _sse(
                "done",
                {
                    "source": "conversation",
                    "used_web_search": False,
                    "threshold": 0.0,
                    "top_score": None,
                    "session_id": (
                        str(saved_session.id)
                        if saved_session is not None
                        else (str(session_id) if session_id is not None else None)
                    ),
                    "user_message_id": str(user_msg.id) if user_msg is not None else None,
                    "assistant_message_id": (
                        str(assistant_msg.id) if assistant_msg is not None else None
                    ),
                    "suggestions": [],
                    "suggested_questions": [],
                },
            )
            return

        if not document_service.class_has_uploaded_documents(db, class_id):
            text = NO_CLASS_DOCUMENTS_MESSAGE
            yield _sse("token", {"text": text})
            trace.append("Class materials: none uploaded")
            trace.append(f"pedagogy:{_tag_pedagogy(message)}")
            saved = _persist_turn(
                db,
                user_id=user_id,
                session_id=session_id,
                class_id=class_id,
                message=message,
                answer=text,
                citations=[],
                trace=trace,
                excluded_from_context=True,
                thinking_ms=int((time.monotonic() - started) * 1000),
            )
            saved_session, user_msg, assistant_msg = saved or (None, None, None)
            yield _sse(
                "done",
                _done_payload(
                    source="none",
                    session_id=saved_session.id if saved_session else session_id,
                    user_message_id=user_msg.id if user_msg else None,
                    assistant_message_id=assistant_msg.id if assistant_msg else None,
                    threshold=0.0,
                    top_score=None,
                    strict_status="none",
                    answer_kind="course",
                    is_homework=is_hw,
                ),
            )
            return

        async with asyncio.timeout(budget):
            yield _sse("progress", {"stage": "searching", "message": "Checking class scope"})
            class_record = course_service.get_class(db, class_id)
            class_name = class_record.name if class_record is not None else ""
            class_description = (
                class_record.info.description
                if class_record is not None and class_record.info is not None
                else None
            )

            scope_decision = await decision_service.is_confidently_out_of_scope(
                class_name=class_name,
                class_description=class_description,
                question=message,
                history=chat_context_service.format_history_context(context_history),
                db=db,
            )
            if scope_decision:
                text = (
                    "This question appears to be outside the scope of this class. "
                    "Please ask a question related to the course subject."
                )
                yield _sse("token", {"text": text})
                trace.append("Scope gate: out of scope")
                trace.append(f"pedagogy:{_tag_pedagogy(message)}")
                saved = _persist_turn(
                    db,
                    user_id=user_id,
                    session_id=session_id,
                    class_id=class_id,
                    message=message,
                    answer=text,
                    citations=[],
                    trace=trace,
                    excluded_from_context=True,
                    thinking_ms=int((time.monotonic() - started) * 1000),
                )
                saved_session, user_msg, assistant_msg = saved or (None, None, None)
                yield _sse(
                    "done",
                    _done_payload(
                        source=rag_service.SOURCE_UNRELATED,
                        session_id=saved_session.id if saved_session else session_id,
                        user_message_id=user_msg.id if user_msg else None,
                        assistant_message_id=assistant_msg.id if assistant_msg else None,
                        threshold=0.0,
                        top_score=None,
                        strict_status="none",
                        answer_kind="course",
                        is_homework=is_hw,
                    ),
                )
                return

            standalone = message
            if context_history:
                try:
                    standalone = await chat_context_service.condense_question(
                        context_history,
                        message,
                        class_name=class_name,
                        class_description=class_description,
                        db=db,
                    )
                except Exception:  # noqa: BLE001 - rewrite is optional
                    logger.warning("Strict chat follow-up rewrite failed; using the original question.")

            yield _sse(
                "progress",
                {"stage": "searching", "message": "Searching class materials"},
            )
            decision = chat_retrieval_service.retrieve_for_chat(
                db,
                question=standalone,
                class_id=class_id,
            )
            chunks = tuple(decision.chunks or ())
            trace.append(
                f"Retrieved {len(chunks)} class sections (score={decision.top_score})"
            )
            filtered = await decision_service.filter_reranked_chunks(
                question=standalone,
                chunks=chunks,
                db=db,
            )
            if len(filtered) != len(chunks):
                trace.append(f"Decision rerank gate kept {len(filtered)} of {len(chunks)} course sections")
            chunks = filtered

            # A published syllabus roadmap is an authoritative class source.
            # It still goes through the same scope gate and strict evidence
            # validator; it is never treated as web or unvalidated context.
            if _is_syllabus_relevant_question(standalone):
                _roadmap_text, roadmap_chunk = _format_syllabus_roadmap(db, class_id)
                if roadmap_chunk is not None:
                    visible_document_ids = document_service.retrievable_document_ids(
                        db, class_id
                    )
                    if roadmap_chunk.document_id in visible_document_ids:
                        # Add the published roadmap; never remove valid retrieved
                        # chunks that happen to share its document ID.
                        chunks = [roadmap_chunk, *chunks]
                        trace.append("Included published syllabus roadmap")
            yield _sse(
                "progress",
                {
                    "stage": "reading",
                    "message": f"Validating {len(chunks)} course sections",
                },
            )

            sources = strict_sources_service.sources_from_chunks(chunks, prefix="")
            try:
                result = await strict_sources_service.generate_strict_sources_answer(
                    question=standalone,
                    sources=sources,
                    db=db,
                    model_invoker=strict_model_invoker,
                    timeout_seconds=max(1.0, budget - (time.monotonic() - started)),
                )
            except strict_sources_service.StrictSourcesError:
                logger.warning("Strict-source validation failed; failing closed.", exc_info=True)
                yield _sse("error", {"message": STRICT_GENERATION_ERROR_MESSAGE})
                return

            conflict_warning = _conflict_warning(result)
            conflict_ids = _conflict_source_ids(result)
            composed_answer = ""
            supported_intents = [
                intent for intent in result.intents if intent.status == "supported"
            ]
            composer_sources = sorted(
                {
                    str(source_id)
                    for intent in supported_intents
                    for source_id in intent.source_ids
                }
            )
            composer_question = standalone
            if result.status == "partial":
                composer_question = " ".join(
                    intent.question_segment.strip() for intent in supported_intents
                ).strip()
            if (
                result.status in ("full", "partial")
                and supported_intents
                and composer_sources
                and not is_hw
                and budget - (time.monotonic() - started) > 3.0
            ):
                composer_budget = min(
                    document_answer_service.DOCUMENT_ANSWER_TIMEOUT_SECONDS,
                    max(0.1, budget - (time.monotonic() - started) - 2.0),
                )
                try:
                    composed_answer = await document_answer_service.compose_document_answer(
                        db,
                        question=composer_question,
                        chunks=chunks,
                        source_ids=composer_sources,
                        timeout_seconds=composer_budget,
                    )
                except Exception:
                    logger.warning(
                        "Document answer composition failed; using the validated draft.",
                        exc_info=True,
                    )
            if result.status == "full":
                answer = composed_answer or (result.answer or "").strip()
                if not answer:
                    yield _sse("error", {"message": STRICT_GENERATION_ERROR_MESSAGE})
                    return
                citations = _source_citations(chunks, result.source_ids_used)
                kind = "full"
                source = rag_service.SOURCE_CURRICULUM
            elif result.status == "partial":
                answer = composed_answer or (result.answer or "").strip()
                if not answer:
                    yield _sse("error", {"message": STRICT_GENERATION_ERROR_MESSAGE})
                    return
                if conflict_warning:
                    answer = f"{answer}\n\n{conflict_warning}"
                citations = _source_citations(
                    chunks,
                    [*result.source_ids_used, *conflict_ids],
                )
                kind = "partial"
                source = rag_service.SOURCE_CURRICULUM
            else:
                answer = NO_COURSE_EVIDENCE_MESSAGE
                if conflict_warning:
                    answer = f"{answer}\n\n{conflict_warning}"
                citations = _source_citations(chunks, conflict_ids)
                kind = "none"
                source = "none"

            yield _sse("progress", {"stage": "drafting", "message": "Drafting validated answer"})
            first_token_ms = int((time.monotonic() - started) * 1000)
            for part in _answer_chunks(answer):
                yield _sse("token", {"text": part})
            for citation in citations:
                yield _sse("citation", _citation_dict(citation))

            followup_questions: list[str] = []
            remaining = budget - (time.monotonic() - started)
            if kind in ("full", "partial") and remaining > 1.0:
                try:
                    followup_questions = await asyncio.wait_for(
                        suggestion_service.generate_followup_questions(
                            question=standalone,
                            answer=answer,
                            chunks=chunks,
                            history=chat_context_service.format_history_context(context_history),
                            model=None,
                            db=db,
                        ),
                        timeout=min(
                            SUGGESTION_PREFETCH_GRACE_SECONDS,
                            max(0.1, remaining - 1.0),
                        ),
                    )
                except Exception:
                    logger.warning(
                        "Suggestion prefetch failed; using fallback suggestions.",
                        exc_info=True,
                    )
                    followup_questions = []
                if not followup_questions:
                    followup_questions = suggestion_service.build_fallback_followups(
                        question=message,
                        class_name=class_name,
                        chunks=chunks,
                    )

            trace.append(f"pedagogy:{_tag_pedagogy(message)}")
            fallback_reason = _fallback_reason(result, decision)
            saved = _persist_turn(
                db,
                user_id=user_id,
                session_id=session_id,
                class_id=class_id,
                message=message,
                answer=answer,
                citations=[_citation_dict(citation) for citation in citations],
                suggested_questions=followup_questions or None,
                trace=trace,
                thinking_ms=first_token_ms,
                query_embedding=list(decision.query_vector) if decision.query_vector else None,
                fallback_reason=fallback_reason,
            )
            saved_session, user_msg, assistant_msg = saved or (None, None, None)
            resolved_session_id = saved_session.id if saved_session else session_id

            if assistant_msg is not None and user_id is not None:
                try:
                    _schedule_content_gap_sync(
                        message_id=str(assistant_msg.id),
                        class_id=str(class_id),
                        student_id=str(user_id),
                        embedding=decision.query_vector or None,
                        fallback_reason=fallback_reason,
                    )
                except Exception:
                    logger.warning(
                        "Could not schedule content-gap telemetry for message %s.",
                        assistant_msg.id,
                        exc_info=True,
                    )

            offer = None
            if (
                result.status in ("partial", "none")
                and user_id is not None
                and resolved_session_id is not None
            ):
                offer = web_consent_service.create_offer_for_result(
                    db,
                    user_id=user_id,
                    class_id=uuid.UUID(str(class_id)),
                    session_id=resolved_session_id,
                    assistant_message_id=assistant_msg.id if assistant_msg else None,
                    question=message,
                    result=result,
                    conflict_note=conflict_warning,
                    conflict_citations=[
                        _citation_dict(citation)
                        for citation in _source_citations(chunks, conflict_ids)
                    ],
                )
                if offer is not None:
                    yield _sse("consent", web_consent_service.offer_read(offer).model_dump(mode="json"))

            if followup_questions:
                yield _sse("suggestions", {"questions": followup_questions})

            yield _sse(
                "done",
                _done_payload(
                    source=source,
                    session_id=resolved_session_id,
                    user_message_id=user_msg.id if user_msg else None,
                    assistant_message_id=assistant_msg.id if assistant_msg else None,
                    threshold=decision.threshold,
                    top_score=decision.top_score,
                    strict_status=kind,
                    answer_kind="course",
                    is_homework=is_hw,
                    consent_offer_id=offer.id if offer is not None else None,
                    suggested_questions=followup_questions,
                ),
            )
    except TimeoutError:
        logger.warning("Strict chat turn timed out for class %s.", class_id)
        yield _sse("error", {"message": TIMEOUT_ERROR_MESSAGE})
    except Exception:
        logger.exception("Strict chat turn failed for class %s.", class_id)
        yield _sse("error", {"message": GENERATION_ERROR_MESSAGE})


async def decide_consent(
    *,
    db: Session,
    user_id: uuid.UUID,
    offer_id: uuid.UUID,
    class_id: uuid.UUID,
    session_id: uuid.UUID,
    decision: str,
    search_fn: rag_service.InternetSearch | None = None,
    timeout_seconds: float | None = None,
) -> WebConsentResult | AsyncIterator[str]:
    """Decline one offer, or claim it and return its SSE web-answer stream.

    The accepted path uses the established SerpApi-snippet answer flow. It never
    runs class retrieval, never receives course chunks/history, and never
    fetches result pages into a second evidence-validation pipeline.
    """

    if decision == "decline":
        offer = web_consent_service.decline_offer(
            db,
            user_id=user_id,
            offer_id=offer_id,
            class_id=class_id,
            session_id=session_id,
        )
        return WebConsentResult(
            offer_id=offer.id,
            status="declined",
            assistant_message_id=offer.assistant_message_id,
        )

    offer, claim = web_consent_service.claim_offer(
        db,
        user_id=user_id,
        offer_id=offer_id,
        class_id=class_id,
        session_id=session_id,
    )
    if claim == "already_consumed":
        return _consumed_result(db, offer)

    return stream_web_consent(
        db=db,
        offer=offer,
        search_fn=search_fn,
        timeout_seconds=timeout_seconds,
    )


async def stream_web_consent(
    *,
    db: Session,
    offer: Any,
    search_fn: rag_service.InternetSearch | None = None,
    timeout_seconds: float | None = None,
) -> AsyncIterator[str]:
    """Stream progress, model tokens, citations, and the persisted web answer.

    Only a complete answer is persisted. Any search, model, persistence, or
    client-stream failure releases the claimed offer so the user can retry.
    """

    budget = (
        timeout_seconds
        if timeout_seconds is not None
        else settings.chat_timeout_seconds
    )
    started = time.monotonic()
    completed = False
    released = False

    def release_once() -> None:
        nonlocal released
        if released:
            return
        released = True
        web_consent_service.release_offer(db, offer=offer)

    try:
        async with asyncio.timeout(budget):
            yield _sse(
                "progress",
                {"stage": "searching", "message": "Searching the web"},
            )

            searcher = search_fn or rag_service.search_internet
            try:
                results = list(await asyncio.to_thread(searcher, offer.query_text))
            except Exception as exc:
                logger.warning(
                    "Strict web diagnostic: web search failed; releasing consent offer."
                )
                raise strict_web_service.WebEvidenceError("Web search failed.") from exc

            if not results:
                logger.warning(
                    "Strict web diagnostic: no usable web search results; "
                    "releasing consent offer."
                )
                raise strict_web_service.WebEvidenceError(
                    "Web search returned no usable results."
                )

            yield _sse(
                "progress",
                {"stage": "drafting", "message": "Writing the web answer"},
            )
            sources, system_prompt, user_prompt = rag_service.prepare_web_answer(
                offer.query_text, results
            )

            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            answer_parts: list[str] = []
            first_token_ms: int | None = None
            async for part in gateway.astream_chat(
                db,
                messages,
                max_output_tokens=settings.chat_answer_max_tokens,
            ):
                if isinstance(part, gateway.StreamRestart):
                    answer_parts.clear()
                    yield _sse("restart", {"message": part.message})
                elif part:
                    if first_token_ms is None:
                        first_token_ms = int((time.monotonic() - started) * 1000)
                    answer_parts.append(part)
                    yield _sse("token", {"text": part})

            answer = "".join(answer_parts).strip()
            if not answer:
                logger.warning(
                    "Strict web diagnostic: web answer was empty; releasing consent offer."
                )
                raise strict_web_service.WebEvidenceError("Web answer was empty.")

            citations = _web_source_links(sources)
            web_suggestion_chunks = [
                rag_service.ScoredChunk(
                    content=result.content,
                    score=1.0,
                    metadata={"title": result.title, "url": result.url},
                )
                for result in results
                if getattr(result, "content", "")
            ]
            followup_questions: list[str] = []
            remaining = budget - (time.monotonic() - started)
            if web_suggestion_chunks and remaining > 1.0:
                try:
                    followup_questions = await asyncio.wait_for(
                        suggestion_service.generate_followup_questions(
                            question=offer.query_text,
                            answer=answer,
                            chunks=web_suggestion_chunks,
                            history="",
                            model=None,
                            db=db,
                        ),
                        timeout=min(
                            SUGGESTION_PREFETCH_GRACE_SECONDS,
                            max(0.1, remaining - 1.0),
                        ),
                    )
                except Exception:
                    logger.warning(
                        "Web suggestion prefetch failed; using fallback suggestions.",
                        exc_info=True,
                    )
                    followup_questions = []
                if not followup_questions:
                    followup_questions = suggestion_service.build_fallback_followups(
                        question=offer.query_text,
                        class_name="",
                        chunks=web_suggestion_chunks,
                    )
            pedagogy_source = getattr(offer, "question", None) or getattr(
                offer, "query_text", ""
            )
            message = history_service.append_message(
                db,
                session_id=offer.session_id,
                role="ASSISTANT",
                content=answer,
                used_web_search=True,
                citations=[_citation_dict(citation) for citation in citations],
                suggested_questions=followup_questions or None,
                thinking_ms=first_token_ms,
                trace=[f"pedagogy:{_tag_pedagogy(pedagogy_source)}"],
            )
            message.parent_message_id = offer.assistant_message_id
            db.commit()
            web_consent_service.complete_offer(
                db, offer=offer, web_message_id=message.id
            )
            completed = True

            # Reuse the course turn's existing point instead of storing a
            # second vector. The in-process flag is set synchronously so a
            # slow material upsert cannot overwrite the consumed-web source;
            # the Qdrant call itself stays off the response path.
            if offer.assistant_message_id is not None:
                try:
                    _schedule_content_gap_source_update(str(offer.assistant_message_id))
                except Exception:
                    logger.warning(
                        "Could not schedule content-gap web update for message %s.",
                        offer.assistant_message_id,
                        exc_info=True,
                    )
            for citation in citations:
                yield _sse("citation", _citation_dict(citation))
            if followup_questions:
                yield _sse("suggestions", {"questions": followup_questions})
            yield _sse(
                "done",
                {
                    "source": rag_service.SOURCE_INTERNET,
                    "used_web_search": True,
                    "threshold": 0.0,
                    "top_score": None,
                    "session_id": str(offer.session_id),
                    "user_message_id": None,
                    "assistant_message_id": str(message.id),
                    "suggestions": followup_questions,
                    "suggested_questions": followup_questions,
                    "strict_status": "web",
                    "answer_kind": "web",
                    "is_homework": False,
                    "consent_offer_id": str(offer.id),
                    "status": "accepted",
                },
            )
    except TimeoutError:
        logger.warning("Web consent stream timed out for session %s.", offer.session_id)
        release_once()
        yield _sse("error", {"message": WEB_CONSENT_TIMEOUT_MESSAGE})
    except strict_web_service.WebEvidenceError:
        release_once()
        yield _sse("error", {"message": WEB_CONSENT_ERROR_MESSAGE})
    except Exception as exc:  # noqa: BLE001 - stream failures must fail closed
        logger.warning(
            "Strict web diagnostic: web answer stream failed (%s); "
            "releasing consent offer.",
            type(exc).__name__,
        )
        release_once()
        yield _sse("error", {"message": WEB_CONSENT_ERROR_MESSAGE})
    finally:
        if not completed:
            release_once()


def _consumed_result(db: Session, offer: Any) -> WebConsentResult:
    from app.models.chat import ChatMessage

    message = db.get(ChatMessage, offer.web_message_id) if offer.web_message_id else None
    if message is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consent offer has already been consumed.",
        )
    return WebConsentResult(
        offer_id=offer.id,
        status="already_consumed",
        answer=message.content,
        citations=[
            ChatCitation.model_validate(citation) for citation in (message.citations or [])
        ],
        suggested_questions=list(message.suggested_questions or []),
        assistant_message_id=message.id,
    )


def _done_payload(
    *,
    source: str,
    session_id: uuid.UUID | None,
    user_message_id: uuid.UUID | None,
    assistant_message_id: uuid.UUID | None,
    threshold: float,
    top_score: float | None,
    strict_status: str,
    answer_kind: str,
    is_homework: bool,
    consent_offer_id: uuid.UUID | None = None,
    suggested_questions: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "source": source,
        "used_web_search": False,
        "threshold": threshold,
        "top_score": top_score,
        "session_id": str(session_id) if session_id is not None else None,
        "user_message_id": str(user_message_id) if user_message_id is not None else None,
        "assistant_message_id": (
            str(assistant_message_id) if assistant_message_id is not None else None
        ),
        "suggestions": list(suggested_questions),
        "suggested_questions": list(suggested_questions),
        "strict_status": strict_status,
        "answer_kind": answer_kind,
        "is_homework": is_homework,
        "consent_offer_id": str(consent_offer_id) if consent_offer_id is not None else None,
    }
