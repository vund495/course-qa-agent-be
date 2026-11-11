"""Service for generating follow-up suggested questions after an answer (AI-125).

Generates 2–3 grounded follow-up questions based on the student's question,
the conversation history, and the retrieved course materials (AC-01 to AC-05).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.config.config import settings
from app.core.prompt_manager import get_prompt_manager
from app.services import language_service
from app.services.llm import gateway
from app.services.rag_service import ScoredChunk

logger = logging.getLogger(__name__)

MIN_FOLLOWUP_QUESTIONS = 1
MAX_FOLLOWUP_QUESTIONS = 3
MIN_CONTEXT_LENGTH = 10


def _extract_message_text(content: Any) -> str:
    """Extract displayable text from a LangChain message response."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    return ""


def _parse_json_questions(raw: str, max_count: int = 3, min_count: int = 1) -> list[str]:
    """Extract and validate a list of question strings from an LLM response."""
    cleaned = raw.strip()
    if not cleaned:
        return []

    # Strip markdown code blocks if the model wrapped output in ```json ... ```
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # Search for JSON array brackets if extra preamble text was emitted
    match = re.search(r"\[\s*.*?\s*\]", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to decode JSON from suggestion response: %s", raw[:200])
        return []

    if not isinstance(data, list):
        return []

    questions: list[str] = []
    for item in data:
        if isinstance(item, str):
            q = item.strip().strip('"').strip("'").strip()
            if q:
                if not q.endswith("?"):
                    q = f"{q}?"
                if q not in questions:
                    questions.append(q)

    if len(questions) < min_count:
        return []

    return questions[:max_count]


_VIETNAMESE_CHARS = set("ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ")


def _is_vietnamese(text: str) -> bool:
    return language_service.is_vietnamese(text)


def _extract_clean_topic(question: str) -> str:
    cleaned = re.sub(r"[?!.,;:\"']+", "", question).strip()
    patterns = [
        r"^(?:write|create|implement|explain|describe|what is|what are|how to use|how does|compare|how do)\s+",
        r"^(?:viết|hãy viết|giải thích|cho biết|hướng dẫn|thế nào là|như thế nào|so sánh|làm sao để|tìm hiểu về)\s+",
    ]
    for pat in patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned if len(cleaned) >= 3 else ""


def build_fallback_followups(
    *,
    question: str,
    class_name: str = "",
    chunks: Sequence[ScoredChunk] = (),
) -> list[str]:
    """Generate 2-3 logical follow-up questions from available material context matching the question language."""
    results: list[str] = []
    is_vi = _is_vietnamese(question)
    q_lower = question.lower()
    topic = _extract_clean_topic(question) or class_name or ("chủ đề này" if is_vi else "this topic")

    # Check if chunks have titles or topic keywords
    for chunk in chunks[:3]:
        title = (chunk.title or "").replace(".pdf", "").replace(".docx", "").strip()
        if title and title.lower() not in {"course material", "unknown"}:
            if is_vi:
                results.append(f"Bạn có thể giải thích thêm về nội dung trong phần '{title}' không?")
            else:
                results.append(f"Could you explain more about the contents in '{title}'?")
            if len(results) >= 2:
                break

    if is_vi:
        if any(kw in q_lower for kw in ("hello world", "chương trình đầu", "first program", "bắt đầu c++")):
            results.append("Hàm main() đóng vai trò là điểm bắt đầu thực thi chương trình như thế nào?")
            results.append("Sự khác biệt giữa câu lệnh cout và printf trong C++ là gì?")
            results.append("Tại sao cần chỉ thị tiền xử lý #include <iostream> trong C++?")
        elif any(kw in q_lower for kw in ("con trỏ", "pointer", "ptr", "bộ nhớ", "tham chiếu", "reference")):
            results.append("Sự khác biệt giữa con trỏ (pointer) và tham chiếu (reference) trong C++ là gì?")
            results.append("Làm thế nào để tránh lỗi con trỏ treo (dangling pointer) và rò rỉ bộ nhớ?")
            results.append("Toán tử new và delete quản lý bộ nhớ động như thế nào?")
        elif any(kw in q_lower for kw in ("hàm", "function", "đệ quy", "recursion")):
            results.append("Điều kiện dừng (base case) quan trọng như thế nào trong hàm đệ quy?")
            results.append("Ưu và nhược điểm giữa đệ quy và vòng lặp lặp lại (iteration) là gì?")
            results.append("Cơ chế truyền tham trị và truyền tham chiếu trong hàm khác nhau thế nào?")
        elif any(kw in q_lower for kw in ("vòng lặp", "loop", "for", "while", "do-while")):
            results.append("Khi nào nên dùng vòng lặp for thay vì vòng lặp while?")
            results.append("Lệnh break và continue hoạt động khác nhau như thế nào trong vòng lặp?")
            results.append("Vòng lặp do-while khác với while ở đặc điểm cốt lõi nào?")
        elif any(kw in q_lower for kw in ("class", "lớp", "oop", "đối tượng", "object", "kế thừa", "đa hình")):
            results.append("Sự khác biệt giữa các quyền truy cập private, protected và public là gì?")
            results.append("Hàm tạo (constructor) và hàm hủy (destructor) hoạt động như thế nào?")
            results.append("Khái niệm tính đa hình (polymorphism) được triển khai thế nào trong C++?")
        elif any(kw in q_lower for kw in ("syllabus", "roadmap", "lịch trình", "unit", "outline", "grading", "điểm")):
            results.append("Tiêu chí và tỷ lệ tính điểm môn học được quy định như thế nào?")
            results.append("Môn học có những yêu cầu tiên quyết nào trước khi học?")
            results.append("Lịch trình các bài kiểm tra và bài tập lớn diễn ra khi nào?")
        else:
            results.append(f"Những lưu ý quan trọng và lỗi thường gặp khi làm việc với {topic} là gì?")
            results.append(f"Có những trường hợp thực tế nào nên áp dụng {topic}?")
            results.append(f"Làm thế nào để tối ưu hóa hiệu năng khi sử dụng {topic}?")
    else:
        if any(kw in q_lower for kw in ("hello world", "first program", "getting started")):
            results.append("How does the main() function serve as the execution entry point in C++?")
            results.append("What is the difference between cout and printf in C++?")
            results.append("Why is the #include <iostream> preprocessor directive required?")
        elif any(kw in q_lower for kw in ("pointer", "ptr", "memory", "reference")):
            results.append("What is the difference between a pointer and a reference in C++?")
            results.append("How can dangling pointers and memory leaks be avoided?")
            results.append("How do new and delete operators manage dynamic memory in C++?")
        elif any(kw in q_lower for kw in ("function", "recursion", "recursive")):
            results.append("Why is a base case essential in a recursive function?")
            results.append("What are the advantages and trade-offs between recursion and iteration?")
            results.append("What is the difference between pass-by-value and pass-by-reference in C++?")
        elif any(kw in q_lower for kw in ("loop", "for", "while", "do-while")):
            results.append("When is it best to use a for loop instead of a while loop?")
            results.append("How do break and continue statements behave differently in loops?")
            results.append("How does a do-while loop differ fundamentally from a while loop?")
        elif any(kw in q_lower for kw in ("class", "oop", "object", "inheritance", "polymorphism")):
            results.append("What are the differences between private, protected, and public access specifiers?")
            results.append("How do constructors and destructors work in C++?")
            results.append("How is polymorphism implemented using virtual functions in C++?")
        elif any(kw in q_lower for kw in ("syllabus", "roadmap", "schedule", "unit", "outline", "grading")):
            results.append("What is the grading policy and weight breakdown for this course?")
            results.append("What are the prerequisites required for this course?")
            results.append("When are the assessments and major assignments scheduled?")
        else:
            results.append(f"What common pitfalls and best practices should be kept in mind regarding {topic}?")
            results.append(f"What are common real-world use cases where {topic} is applied?")
            results.append(f"How can performance and safety be improved when working with {topic}?")

    unique: list[str] = []
    for q in results:
        if q not in unique:
            unique.append(q)
    return unique[:3]


async def _invoke_pool(
    db: Session | None,
    messages: list[SystemMessage | HumanMessage],
    timeout_seconds: float,
) -> str:
    """Invoke through the key-pool gateway so suggestions rotate with chat keys."""

    return await gateway.ainvoke_chat(
        db,
        messages,
        timeout=timeout_seconds,
        avoid_sticky_key=True,
    )


async def generate_followup_questions(
    *,
    question: str,
    answer: str = "",
    chunks: Sequence[ScoredChunk] = (),
    history: str = "",
    model: Any | None = None,
    db: Session | None = None,
) -> list[str]:
    """Generate 2-3 suggested follow-up questions grounded in course materials and chat history."""
    if not settings.chat_suggestions_enabled:
        return []

    cleaned_q = question.strip()
    if not cleaned_q:
        return []

    # Build context from materials (chunks)
    context_parts: list[str] = []
    for idx, chunk in enumerate(chunks[:5], start=1):
        if chunk.content and chunk.content.strip():
            part = f"[{idx}] {chunk.title}\n{chunk.content.strip()}"
            context_parts.append(part)

    if not context_parts:
        context_parts.append(f"Course Material & Concepts:\n{cleaned_q}")

    context_text = "\n\n".join(context_parts)

    try:
        prompt = get_prompt_manager().format(
            "suggest-questions-prompt",
            context=context_text,
            history=history or "(No previous conversation)",
            question=cleaned_q,
            answer=re.sub(r"\s*\[\d+\]", "", answer).strip()
            or (
                "Not available yet - this suggestion is generated in parallel with "
                "the answer. Base the questions on the Course Context and User Question."
            ),
        )

        messages = [
            SystemMessage(content=str(prompt["system-prompt"])),
            HumanMessage(content=str(prompt["user-prompt"])),
        ]
        language_service.enforce_language(messages, language_service.detect_query_language(cleaned_q))

        timeout_sec = max(settings.chat_suggestions_timeout_seconds, 8.0)
        async with asyncio.timeout(timeout_sec):
            if model is not None:
                response = await model.ainvoke(messages)
                raw_output = _extract_message_text(getattr(response, "content", response))
            else:
                raw_output = await _invoke_pool(
                    db,
                    messages,
                    timeout_seconds=timeout_sec,
                )

        parsed = _parse_json_questions(
            raw_output,
            max_count=MAX_FOLLOWUP_QUESTIONS,
            min_count=MIN_FOLLOWUP_QUESTIONS,
        )
        if parsed:
            return parsed
        return build_fallback_followups(question=cleaned_q, chunks=chunks)

    except Exception:
        logger.warning(
            "Failed to generate follow-up questions from model; using material fallback.",
            exc_info=True,
        )
        return build_fallback_followups(question=cleaned_q, chunks=chunks)
