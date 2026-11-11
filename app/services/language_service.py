"""Language detection and prompt enforcement service for Educational RAG.

Provides zero-latency, deterministic language classification between Vietnamese ('vi')
and English ('en'), and enforces strict language adherence on LLM prompts to eliminate
conversational priming / language drift across multi-turn sessions.
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

_VI_DIACRITICS = set(
    "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
    "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ"
)

_VI_WORDS = {
    "la", "gi", "sao", "tai", "nhu", "the", "nao", "khong", "co", "duoc",
    "cho", "ve", "cua", "va", "trong", "khi", "de", "di", "ban", "toi", "minh",
    "giup", "voi", "hoc", "bai", "tai_lieu", "chuong", "phan", "lop", "thay",
    "em", "anh", "chi", "con", "cai", "nay", "do", "kia", "tai_sao", "lam",
    "nen", "phai", "biet", "chua", "roi", "rat", "qua", "hon", "nhat", "v",
    "dc", "ko", "k", "vs", "lieu", "co_the", "nhung", "ma", "chac", "kiem_tra",
    "chay", "he", "thong", "boi", "mat", "danh", "sach", "trang", "chuong_trinh",
}

_EN_WORDS = {
    "what", "why", "how", "when", "where", "which", "who", "whom", "whose",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "can", "could", "should", "would", "will", "shall",
    "may", "might", "must", "the", "a", "an", "this", "that", "these", "those",
    "in", "on", "at", "to", "for", "from", "with", "by", "about", "against",
    "between", "into", "through", "during", "before", "after", "above", "below",
    "and", "or", "but", "if", "because", "as", "until", "while", "of", "than",
    "explain", "difference", "compare", "summary", "summarize", "describe", "show",
    "please", "help", "tell", "give", "write", "code", "example", "faster",
    "pitfalls", "practices", "regarding", "advantages", "disadvantages", "overview",
    "best", "better", "memory", "compile", "compiler", "runtime", "performance",
}


def detect_query_language(text: str) -> str:
    """Detect whether user query is Vietnamese ('vi') or English ('en')."""
    if not text:
        return "en"
    if any(c in _VI_DIACRITICS for c in text):
        return "vi"
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words:
        return "en"
    vi_count = sum(1 for w in words if w in _VI_WORDS)
    en_count = sum(1 for w in words if w in _EN_WORDS)
    if vi_count > en_count:
        return "vi"
    if en_count > vi_count:
        return "en"
    return "en"


def is_vietnamese(text: str) -> bool:
    """Convenience boolean check for Vietnamese queries."""
    return detect_query_language(text) == "vi"


def enforce_language(
    messages: list[SystemMessage | HumanMessage],
    query_lang: str,
) -> None:
    """Prepend/append strict language directives to system and user prompts.

    This breaks autoregressive conversational priming (e.g. continuing in Vietnamese
    when the conversation history was in Vietnamese but the current query is in English).
    """
    if not messages:
        return

    if query_lang == "vi":
        vi_system = (
            "\n\n### YÊU CẦU NGÔN NGỮ BẮT BUỘC (CRITICAL LANGUAGE MANDATE):\n"
            "Câu hỏi của người dùng bằng TIẾNG VIỆT.\n"
            "Bạn PHẢI trả lời hoàn toàn bằng TIẾNG VIỆT tự nhiên, chuẩn xác và dễ hiểu.\n"
            "Giữ nguyên các thuật ngữ kỹ thuật, từ khóa code, tên thư viện và cú pháp lập trình bằng tiếng Anh chuẩn.\n"
            "Tuyệt đối không trả lời toàn bộ bài bằng tiếng Anh."
        )
        vi_user = (
            "\n\n[YÊU CẦU NGÔN NGỮ BẮT BUỘC: Câu hỏi bằng TIẾNG VIỆT. "
            "Trả lời hoàn toàn bằng TIẾNG VIỆT (giữ nguyên thuật ngữ kỹ thuật/code).]"
        )
        if isinstance(messages[0], SystemMessage):
            messages[0] = SystemMessage(content=str(messages[0].content) + vi_system)
        if isinstance(messages[-1], HumanMessage):
            messages[-1] = HumanMessage(content=str(messages[-1].content) + vi_user)
    else:
        en_system = (
            "\n\n### CRITICAL LANGUAGE MANDATE:\n"
            "The user's question is in ENGLISH.\n"
            "You MUST respond 100% in ENGLISH.\n"
            "DO NOT output Vietnamese words, phrases, or boilerplates (such as 'Dựa trên...', 'không có thông tin chi tiết', etc.), "
            "regardless of what language was used in the previous conversation history or retrieved materials.\n"
            "Every explanation, heading, table, and sentence MUST be in fluent English."
        )
        en_user = (
            "\n\n[MANDATORY LANGUAGE INSTRUCTION: The question is in ENGLISH. "
            "Answer 100% in ENGLISH only. Do NOT use Vietnamese.]"
        )
        if isinstance(messages[0], SystemMessage):
            messages[0] = SystemMessage(content=str(messages[0].content) + en_system)
        if isinstance(messages[-1], HumanMessage):
            messages[-1] = HumanMessage(content=str(messages[-1].content) + en_user)

