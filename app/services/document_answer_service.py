"""Compose a course-document answer with the pre-AI-194 document prompt.

AI-194 added the strict full/partial/none evidence classifier but drafted the
user-facing answer from the classifier's short explanations. This module keeps
that classifier intact and only restores the old document answer composition
(``answer-course-prompt``), which supports code blocks and full explanations.

It fails closed: a missing or out-of-range source id returns no answer, so the
caller keeps the validated strict draft instead of falling back to every
retrieved chunk.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.core.prompt_manager import get_prompt_manager
from app.services import rag_service
from app.services.llm import gateway

logger = logging.getLogger(__name__)

ANSWER_COURSE_PROMPT = "answer-course-prompt"
EMPTY_HISTORY = "(No previous conversation.)"
DOCUMENT_ANSWER_TIMEOUT_SECONDS = 20.0


class DocumentAnswerError(RuntimeError):
    """The document answer could not be composed from the validated sources."""


def _numbered_chunks(
    chunks: Sequence[rag_service.ScoredChunk],
    source_ids: Sequence[str],
) -> list[tuple[int, rag_service.ScoredChunk]]:
    """Return only the validated chunks, keeping their original marker numbers."""

    wanted = [str(source_id) for source_id in source_ids if str(source_id).strip()]
    if not wanted:
        return []
    available = {str(index) for index in range(1, len(chunks) + 1)}
    if any(source_id not in available for source_id in wanted):
        return []
    indexes = sorted({int(source_id) for source_id in wanted})
    return [(index, chunks[index - 1]) for index in indexes]


def marker_indexes(answer: str) -> set[int]:
    """Use the shared citation parser: it skips code/math and grouped markers."""

    return rag_service.cited_markers(answer or "")


def build_document_answer_messages(
    *,
    question: str,
    chunks: Sequence[rag_service.ScoredChunk],
    source_ids: Sequence[str],
) -> list[SystemMessage | HumanMessage]:
    """Render the old course-answer prompt with only the validated sources.

    The question is already standalone (the follow-up condense step ran before
    this call), so conversation history is deliberately not sent again.
    """

    numbered = _numbered_chunks(chunks, source_ids)
    if not numbered:
        raise DocumentAnswerError("No validated source chunks are available.")
    cleaned = (question or "").strip()
    if not cleaned:
        raise DocumentAnswerError("Question must not be empty.")

    context = "\n\n".join(
        rag_service._curriculum_context_line(index, chunk)
        for index, chunk in numbered
    )
    prompt = get_prompt_manager().format(
        ANSWER_COURSE_PROMPT,
        context=context,
        question=cleaned,
        history=EMPTY_HISTORY,
    )
    return [
        SystemMessage(content=str(prompt["system-prompt"])),
        HumanMessage(content=str(prompt["user-prompt"])),
    ]


async def compose_document_answer(
    db: Session,
    *,
    question: str,
    chunks: Sequence[rag_service.ScoredChunk],
    source_ids: Sequence[str],
    timeout_seconds: float = DOCUMENT_ANSWER_TIMEOUT_SECONDS,
) -> str:
    """Ask the model for the old-style document answer over validated chunks."""

    numbered = _numbered_chunks(chunks, source_ids)
    messages = build_document_answer_messages(
        question=question,
        chunks=chunks,
        source_ids=source_ids,
    )
    allowed = {index for index, _chunk in numbered}
    answer = await asyncio.wait_for(
        gateway.ainvoke_chat(db, messages),
        timeout=timeout_seconds,
    )
    text = (answer or "").strip()
    if not text:
        raise DocumentAnswerError("The document answer was empty.")
    if not marker_indexes(text) <= allowed:
        raise DocumentAnswerError("The document answer cited a source outside the validated set.")
    return text
