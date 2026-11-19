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

from sqlalchemy.orm import Session

from app.config.config import settings
from app.schemas.chat import WebConsentResult
from app.schemas.history import ChatCitation
from app.services import (
    chat_context_service,
    chat_retrieval_service,
    course_service,
    decision_service,
    document_service,
    history_service,
    rag_service,
    strict_sources_service,
    strict_web_service,
    web_consent_service,
)
from app.services.chat_context_service import ConversationExchange
from app.services.chat_service import (
    _HOMEWORK_PATTERNS,
    GENERATION_ERROR_MESSAGE,
    TIMEOUT_ERROR_MESSAGE,
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
    excluded_from_context: bool = False,
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
            trace=trace,
            excluded_from_context=excluded_from_context,
        )
    except Exception:
        logger.exception("Failed to persist strict-source chat turn.")
        return None


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
        if not document_service.class_has_uploaded_documents(db, class_id):
            text = NO_CLASS_DOCUMENTS_MESSAGE
            yield _sse("token", {"text": text})
            trace.append("Class materials: none uploaded")
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

        if user_id is not None and session_id is not None:
            web_consent_service.expire_pending_offers(
                db,
                user_id=user_id,
                session_id=session_id,
            )
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
            if result.status == "full":
                answer = (result.answer or "").strip()
                if not answer:
                    yield _sse("error", {"message": STRICT_GENERATION_ERROR_MESSAGE})
                    return
                citations = _source_citations(chunks, result.source_ids_used)
                kind = "full"
                source = rag_service.SOURCE_CURRICULUM
            elif result.status == "partial":
                answer = (result.answer or "").strip()
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
            for part in _answer_chunks(answer):
                yield _sse("token", {"text": part})
            for citation in citations:
                yield _sse("citation", _citation_dict(citation))

            saved = _persist_turn(
                db,
                user_id=user_id,
                session_id=session_id,
                class_id=class_id,
                message=message,
                answer=answer,
                citations=[_citation_dict(citation) for citation in citations],
                trace=trace,
            )
            saved_session, user_msg, assistant_msg = saved or (None, None, None)
            resolved_session_id = saved_session.id if saved_session else session_id

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
            async for part in gateway.astream_chat(
                db,
                messages,
                max_output_tokens=settings.chat_answer_max_tokens,
            ):
                if isinstance(part, gateway.StreamRestart):
                    answer_parts.clear()
                    yield _sse("restart", {"message": part.message})
                elif part:
                    answer_parts.append(part)
                    yield _sse("token", {"text": part})

            answer = "".join(answer_parts).strip()
            if not answer:
                logger.warning(
                    "Strict web diagnostic: web answer was empty; releasing consent offer."
                )
                raise strict_web_service.WebEvidenceError("Web answer was empty.")

            citations = rag_service.cited_web_citations(sources, answer)
            message = history_service.append_message(
                db,
                session_id=offer.session_id,
                role="ASSISTANT",
                content=answer,
                used_web_search=True,
                citations=[_citation_dict(citation) for citation in citations],
            )
            message.parent_message_id = offer.assistant_message_id
            db.commit()
            web_consent_service.complete_offer(
                db, offer=offer, web_message_id=message.id
            )
            completed = True

            for citation in citations:
                yield _sse("citation", _citation_dict(citation))
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
                    "suggestions": [],
                    "suggested_questions": [],
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
        "suggestions": [],
        "suggested_questions": [],
        "strict_status": strict_status,
        "answer_kind": answer_kind,
        "is_homework": is_homework,
        "consent_offer_id": str(consent_offer_id) if consent_offer_id is not None else None,
    }
