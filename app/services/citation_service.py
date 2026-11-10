"""Citations helper service for deep-linking and text fragment generation."""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Iterator, Sequence
from typing import Any

from app.services.ingestion.chunker import _fenced_ranges
from app.services.ingestion.cleaner import _PROTECTED, _protect, _restore, _strip_emphasis

_MARKER_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_LIST_ITEM_PATTERN = re.compile(
    r"(?m)^[ \t]*(?:[-+*]|\d+[.)])[ \t]+[^\n]*"
    r"(?:\n(?![ \t]*(?:$|#{1,6}[ \t]|[-+*][ \t]|\d+[.)][ \t]))[^\n]+"
    r"|\n[ \t]*\n[ \t]{2,}[^\n]+)*"
)


def _clean_snippet(text: str) -> str:
    """Strip markdown formatting, HTML tags, and normalize whitespace."""
    # Strip HTML tags
    text = re.sub(r"<[^<]+?>", " ", text)
    # Strip markdown links [anchor](url) -> anchor
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Strip markdown formatting symbols (bold, italic, code, headers, bullets)
    text = re.sub(r"[*_`#~|]", " ", text)
    return text.strip()


def normalize_search_url(url: str | None) -> str:
    """Make provider-relative redirect URLs safe to store and open."""
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    if cleaned.startswith("//"):
        cleaned = f"https:{cleaned}"
    if cleaned.startswith(("/goto?url=", "goto?url=")):
        return f"https://www.google.com/{cleaned.lstrip('/')}"
    return cleaned


def _clean_word(w: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", w)


def _encode_text_directive(text: str) -> str:
    """Percent-encode text directive according to W3C Scroll-to-Text-Fragment spec.

    Hyphens, ampersands, and commas carry syntactic meaning in the directive
    ('-', '&', ',') and must be explicitly percent-encoded.
    """
    encoded = urllib.parse.quote(text)
    return encoded.replace("-", "%2D").replace("&", "%26").replace(",", "%2C")


def build_universal_jump_url(base_url: str, snippet: str | None = None) -> str:
    """Build a universal W3C Scroll-to-Text-Fragment URL.

    Uses range directive `#:~:text=textStart,textEnd` to robustly highlight
    the matching excerpt across any web page (e.g. from Tavily search results).
    Targets a coherent sentence or clause to prevent cross-block DOM matching
    failures in Chromium browsers.
    """
    if not base_url:
        return ""
    clean_base = normalize_search_url(base_url).split("#")[0]
    if not snippet or not snippet.strip():
        return clean_base

    cleaned = _clean_snippet(snippet)

    # Split into candidate sentences or lines to target a single coherent DOM block
    sentences = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    candidate_words: list[str] = []
    for s in sentences:
        s_norm = re.sub(r"\s+", " ", s).strip()
        words = [_clean_word(w) for w in s_norm.split(" ") if _clean_word(w)]
        if len(words) >= 5:
            candidate_words = words
            break

    if not candidate_words:
        s_norm = re.sub(r"\s+", " ", cleaned).strip()
        candidate_words = [_clean_word(w) for w in s_norm.split(" ") if _clean_word(w)]

    if not candidate_words:
        return clean_base

    # For short phrases (<= 5 words), exact match is safest
    if len(candidate_words) <= 5:
        query = " ".join(candidate_words)
        return f"{clean_base}#:~:text={_encode_text_directive(query)}"

    # Range syntax within a single coherent sentence: take first 4 words and last 4 words
    text_start = " ".join(candidate_words[:4])
    text_end = " ".join(candidate_words[-4:])

    if not text_start:
        return clean_base
    if not text_end or text_start == text_end:
        return f"{clean_base}#:~:text={_encode_text_directive(text_start)}"

    return f"{clean_base}#:~:text={_encode_text_directive(text_start)},{_encode_text_directive(text_end)}"


_INTRO_BOILERPLATE_PATTERN = re.compile(
    r"^(?:"
    r"we have provided|"
    r"click on this link|"
    r"try to click|"
    r"the basic structure of|"
    r"let us (?:look|see|discuss|examine|consider|have)|"
    r"let\'s (?:look|see|discuss|examine|consider|have)|"
    r"make sure that|"
    r"in this (?:chapter|section|tutorial|unit|lecture|lesson)|"
    r"here is (?:a|an|the)|"
    r"following is (?:a|an|the)|"
    r"to start with|"
    r"welcome to|"
    r"this tutorial|"
    r"before proceeding|"
    r"it is assumed|"
    r"a c\+\+ program can be defined|"
    r"c\+\+ is a (?:middle-level|statically typed|general-purpose)|"
    r"c\+\+ program structure"
    r")",
    re.IGNORECASE,
)


def is_ignorable_passage(
    passage: str,
    *,
    chunk: Any = None,
    current_section: str = "",
) -> bool:
    """Detect running headers, boilerplate filler, and trailing next-section headings.

    Preserves legitimate short points, Roman numeral items (I, II), code blocks,
    and numbered or bulleted list items that carry instructional content.
    """
    raw = passage.strip()
    if not raw:
        return True

    # Code blocks or comparison rows are never ignorable
    if raw.startswith(("```", "~~~", "|")):
        return False

    # Ignore comments and bookmark artifacts
    if re.match(r"^<!--\s*(?:Page|Slide)\s+number:\s*\d+\s*-->", raw, re.IGNORECASE):
        return True
    if re.search(r"\.{5,}|Bookmark not defined", raw, re.IGNORECASE):
        return True
    if re.fullmatch(r"[\s|:\-*_#]+", raw):
        return True

    # Strip markdown wrappers for structural inspection
    clean = re.sub(r"[*_#`]", "", raw).strip()
    if not clean:
        return True

    clean_lower = clean.casefold()

    # Ignore known boilerplate introductory transitions
    if _INTRO_BOILERPLATE_PATTERN.match(clean):
        return True

    # Check for document titles / running watermarks (e.g. 'C++ Tutorial', 'cpp_tutorial')
    doc_titles: set[str] = set()
    if chunk is not None:
        raw_title = getattr(chunk, "title", None) or ""
        meta = getattr(chunk, "metadata", None) or {}
        file_name = meta.get("file_name", "") if isinstance(meta, dict) else ""
        for name in (raw_title, file_name):
            if not name:
                continue
            base = re.sub(r"\.[a-zA-Z0-9]+$", "", str(name)).strip()
            if base:
                doc_titles.add(base.casefold())
                doc_titles.add(base.replace("_", " ").casefold())
                doc_titles.add(base.replace("-", " ").casefold())
                doc_titles.add(base.replace("cpp", "c++").replace("_", " ").casefold())
                doc_titles.add(base.replace("c++", "cpp").replace("_", " ").casefold())

    if clean_lower in doc_titles:
        return True

    # Generic tutorial running headers (e.g. 'C++ Tutorial', 'Python Guide', 'Java Quick Guide')
    if re.fullmatch(
        r"(?:c\+\+|cpp|python|java|javascript|c#|rust|golang|go|sql)?\s*(?:tutorial|quick\s+guide|reference|handbook|cheatsheet)",
        clean_lower,
    ):
        return True

    # List items starting with -, *, • are ALWAYS preserved (unless matching boilerplate/doc title above)
    if raw.startswith(("-", "*", "•")):
        return False

    # Items with terminal punctuation or explanation are ALWAYS preserved
    has_body_punctuation = any(raw.endswith(p) for p in (".", ":", ";", "!", "?", "−", "—"))
    if has_body_punctuation and len(clean.split()) >= 3:
        return False

    # Check for trailing next-chapter / next-section headings that leaked into chunk tail
    # (e.g. '2. C++ Environment Setup**', 'Chapter 2. Environment Setup')
    is_heading_pattern = bool(re.match(
        r"^(?:\d+[.)]|\bChapter\s+\d+[.:]?|[#]{1,6})\s+[A-Za-z0-9+]+(?:\s+[A-Za-z0-9+]+)*$",
        clean,
    ))
    if is_heading_pattern:
        heading_words = set(re.findall(r"\w+", clean_lower)) - {"chapter", "c", "cpp"}
        # Check against common textbook introductory/setup chapter titles
        if any(term in clean_lower for term in ("environment setup", "installation", "getting started", "table of contents")):
            return True
        # If current section is known, check whether this heading belongs to a completely different topic
        if current_section:
            section_words = set(re.findall(r"\w+", current_section.casefold())) - {"c", "cpp"}
            if heading_words and not (heading_words & section_words) and len(clean.split()) <= 6:
                return True
        elif len(clean.split()) <= 5 and not has_body_punctuation:
            return True

    return False


def extract_best_sentence(
    chunk_content: str, target_assertion: str = "", *, question: str = "",
) -> str:
    """Select a source sentence, complete list item, row, or code block verbatim."""
    fragments: list[str] = []
    cursor = 0
    ranges = _fenced_ranges(chunk_content)
    ranges = sorted([*ranges, *(
        match.span() for match in _LIST_ITEM_PATTERN.finditer(chunk_content)
        if not any(start <= match.start() < end for start, end in ranges)
    )])
    for start, end in ranges:
        fragments.extend(re.split(r"(?<=[.!?])\s+|\n+", chunk_content[cursor:start]))
        fragments.append(chunk_content[start:end])
        cursor = end
    fragments.extend(re.split(r"(?<=[.!?])\s+|\n+", chunk_content[cursor:]))
    candidates = list(dict.fromkeys(
        sentence.strip()
        for sentence in fragments
        if sentence.strip()
        and not re.match(r"^\s*#{1,6}\s", sentence)
        and not re.match(r"^<!--\s*(?:Page|Slide)\s+number:\s*\d+\s*-->", sentence, re.IGNORECASE)
        and not re.fullmatch(r"[\s|:\-]+", sentence)
        and not re.search(r"\.{5,}|Bookmark not defined", sentence, re.IGNORECASE)
    ))
    if not candidates:
        return ""

    # Filter out bare running headers, document titles, and introductory boilerplate transitions
    substantive = [
        c for c in candidates
        if (
            c.startswith(("-", "*", "•", "```", "~~~"))
            or any(c.endswith(p) for p in (".", ":", ";", "!", "?", "−", "—"))
            or len(c.split()) > 4
        )
        and not is_ignorable_passage(c)
    ]
    if substantive:
        candidates = substantive

    if not target_assertion:
        for c in candidates:
            if not is_ignorable_passage(c):
                return c
        return candidates[0]
    if target_assertion.startswith(("```", "~~~")):
        code_candidates = [c for c in candidates if c.startswith(("```", "~~~"))]
        if code_candidates:
            body = " ".join("\n".join(target_assertion.splitlines()[1:-1]).split())
            exact = [
                c for c in code_candidates
                if " ".join("\n".join(c.splitlines()[1:-1]).split()) == body
            ]
            if exact:
                return exact[0]
            target_words = _content_words(target_assertion)
            scored = [
                (len(target_words & _content_words(c)), c)
                for c in code_candidates
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored[0][0] > 0:
                return scored[0][1]
            return code_candidates[0]
    target_words = _content_words(target_assertion)
    specific_target_words = target_words - _GENERIC_MATCH_WORDS
    question_words = _content_words(question)
    specific_q_words = question_words - _GENERIC_MATCH_WORDS
    literals = re.findall(r"`([^`\n]+)`", target_assertion)
    literal_pattern = ".*?".join(re.escape(literal) for literal in literals)
    negations = {"not", "never", "no", "không", "chẳng", "chưa"}
    is_contrast_or_table = (
        "|" in target_assertion
        or any(term in target_assertion.casefold() for term in ("while", "whereas", "unlike", "instead", "trong khi", "khác", "thay vì", "so với"))
    )
    scores = []
    for candidate in candidates:
        words = _content_words(candidate)
        negation_match = (
            candidate.startswith(("```", "~~~"))
            or is_contrast_or_table
            or bool(target_words & negations) == bool(words & negations)
        )
        overlap = len(target_words & words) if negation_match else 0
        has_literal = bool(literals) and bool(re.search(literal_pattern, candidate, re.DOTALL))
        total_words = len(target_words) + len(words)
        f1 = (2.0 * overlap / total_words) if total_words > 0 else 0.0

        eligible = (
            overlap > 0
            or has_literal
            or candidate.startswith(("```", "~~~"))
            or (specific_q_words and bool(specific_q_words & words))
        )
        if not eligible:
            scores.append((0, 0, 0.0, 0, 0, False))
            continue

        clean_cand = re.sub(r"^[-*•\d.)\s]+", "", candidate).strip().casefold()
        clean_target = re.sub(r"^[-*•\d.)\s]+", "", target_assertion).strip().casefold()
        is_exact = int(bool(clean_cand) and clean_cand == clean_target)
        is_sub = int(
            bool(clean_cand) and bool(clean_target)
            and len(clean_cand) >= 3 and len(clean_target) >= 3
            and (clean_cand in clean_target or clean_target in clean_cand)
        )
        scores.append((
            is_exact,
            is_sub,
            round(f1, 4),
            overlap,
            len(specific_q_words & words),
            has_literal,
        ))
    best = max(scores) if scores else (0, 0, 0.0, 0, 0, False)
    if best[0] > 0 or best[1] > 0 or best[2] > 0 or best[3] > 0:
        return candidates[scores.index(best)]

    # Fallback 1: match candidate against specific question keywords (for cross-lingual technical terms)
    if specific_q_words:
        q_scores = [len(specific_q_words & _content_words(c)) for c in candidates]
        if max(q_scores) > 0:
            return candidates[q_scores.index(max(q_scores))]

    # Fallback 2: prefer code candidate ONLY if specific assertion/question terms match the code block
    code_candidates = [c for c in candidates if c.startswith(("```", "~~~"))]
    if code_candidates:
        key_terms = specific_target_words | specific_q_words
        if key_terms:
            code_scores = [len(key_terms & _content_words(c)) for c in code_candidates]
            if max(code_scores) > 0:
                return code_candidates[code_scores.index(max(code_scores))]

    # If specific question terms exist, but neither the question nor the target matches the chunk,
    # the chunk is completely irrelevant to the cited claim. Return "".
    if specific_q_words and not (specific_q_words & _content_words(chunk_content)) and not (specific_target_words & _content_words(chunk_content)):
        return ""

    # Pick the first substantive candidate that is not boilerplate
    for c in candidates:
        if not _INTRO_BOILERPLATE_PATTERN.match(c.strip()):
            return c
    return candidates[0] if candidates else ""


# Common function words ignored during overlap validation
STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with", "by", "of",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "that", "this", "these", "those", "it", "they", "we", "you", "i", "he", "she",
    "là", "và", "hoặc", "trong", "ở", "tại", "đến", "cho", "với", "bởi", "của", "được",
    "có", "những", "các", "này", "đó", "khi", "để", "thì", "mà", "như", "ra", "vào",
    "tôi", "bạn", "mình", "chúng", "ta", "giúp", "hãy", "xin", "bằng", "về",
    "theo", "nào", "sao", "thế", "gì", "bao", "nhiêu", "ai", "đâu",
}

# Generic domain and preamble words that must not validate citation relevance by themselves
_GENERIC_MATCH_WORDS = {
    "c++", "cpp", "csharp", "java", "python", "javascript", "code", "coding",
    "program", "programs", "programming", "programmer", "example", "examples",
    "tutorial", "tutorials", "chapter", "chapters", "lesson", "lessons",
    "unit", "units", "section", "sections", "overview", "introduction",
    "course", "courses", "lecture", "lectures", "student", "students",
    "learn", "study", "language", "languages", "write", "print", "line", "lines",
    "compiler", "compilers", "online", "basic", "structure", "point", "points", "item", "items",
    "lập", "trình", "bài", "tập", "học", "ví", "dụ", "viết", "chương", "mã", "nguồn", "ngôn", "ngữ", "khái", "niệm", "phần", "cấu", "trúc", "cơ", "bản", "mục", "điểm",
    "hàm", "tính", "số", "gặp", "giá", "trị", "lớn", "nhỏ", "nhiều", "ít", "khi", "nào", "sao",
    # Generic algorithmic and complexity descriptor words
    "complexity", "complex", "time", "space", "average", "worst", "best", "case",
    "analysis", "selection", "method", "methods", "approach", "problem", "problems",
    "theory", "concept", "concepts", "definition", "meaning", "system", "systems", "model", "models",
    "phức", "tạp", "thời", "gian", "không", "trung", "bình", "tốt", "xấu", "nhất", "độ",
    "chọn", "lựa", "cách", "phương", "pháp", "toán", "thuật", "giải",
}


def _stem(word: str) -> str:
    """Normalize English and technical plurals (e.g. classes -> class, OOPs -> oop)."""
    w = word.casefold()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "shes", "ches", "xes", "zes")) and len(w) > 4:
        return w[:-2]
    if w.endswith("es") and len(w) > 3 and not w.endswith("sses"):
        return w[:-2]
    if w.endswith("s") and len(w) > 2 and not w.endswith("ss"):
        return w[:-1]
    return w


def _content_words(text: str) -> set[str]:
    """Keep technical identifiers and comment/trigraph operators in lexical matching."""
    text, blocks = _protect(text)
    text = _restore(_strip_emphasis(text), blocks)
    normalized = re.sub(r"\bc\+\+", "cpp", text.casefold())
    normalized = re.sub(r"\bc\#", "csharp", normalized)
    raw_words = {
        word for word in re.findall(
            r"\w+(?:[-.]\w+)*|/\*|\*/|//|\?\?[=/'()!<>-]", normalized,
        )
        if len(word) > 1 and word not in STOPWORDS
    }
    return raw_words | {_stem(w) for w in raw_words}


def _section_terms(text: str) -> set[str]:
    """Normalize regular plurals only for section-intent matching."""
    return {
        word.removesuffix("s") if len(word) > 3 and not word.endswith("ss") else word
        for word in _content_words(text)
    }


def _cited_assertions(answer: str) -> Iterator[tuple[re.Match[str], str]]:
    """Associate markers with preceding paragraphs or code, preserving soft wraps."""
    # Some generated answers put citations directly after a closing fence.
    unmarked = _MARKER_PATTERN.sub(lambda match: " " * len(match[0]), answer)
    fences = _fenced_ranges(unmarked)
    for position, (start, end) in enumerate(fences):
        line_start = answer.rfind("\n", start, end - 1) + 1
        trailing = _MARKER_PATTERN.search(answer, line_start, end)
        if trailing and re.fullmatch(r"[ \t]*(?:`{3,}|~{3,})[ \t]*", answer[line_start:trailing.start()]):
            fences[position] = (start, trailing.start())
    unfenced = list(answer)
    for start, end in fences:
        unfenced[start:end] = ["\n" if char == "\n" else " " for char in answer[start:end]]
    protected = [*fences, *(match.span() for match in _PROTECTED.finditer("".join(unfenced)))]
    previous_end = 0
    previous_assertion = ""
    for match in _MARKER_PATTERN.finditer(answer):
        if any(start <= match.start() < end for start, end in protected):
            continue
        prefix = answer[previous_end:match.start()].strip(" \t\r\n.,;:")
        assertion = re.split(
            r"\n[ \t]*\n|\n(?=[ \t]*(?:#{1,6}[ \t]|[-+*][ \t]|\d+[.)][ \t]|\|[ \t]*))",
            prefix,
        )[-1] if prefix else previous_assertion
        assertion = re.sub(r"(?m)^#{1,6}[ \t]+[^\n]*(?:\n|$)", "", assertion).strip()
        if "|" in assertion:
            assertion = re.sub(r"\|", " ", assertion).strip()
        for start, end in reversed(fences):
            if end <= match.start() and not _MARKER_PATTERN.sub("", answer[end:match.start()]).strip():
                assertion = answer[start:end].strip()
                break
        for start, end in fences:
            if start >= match.end() and not answer[match.end():start].strip(" \t\r\n:"):
                assertion = answer[start:end].strip()
                break
        yield match, assertion
        previous_end = match.end()
        previous_assertion = assertion


def cited_markers(answer: str) -> set[int]:
    """Read explicit source markers while ignoring indexes inside code or math."""
    return {
        int(index) for match, _assertion in _cited_assertions(answer)
        for index in match.group(1).split(",")
    }


def _verified_citations(
    answer: str, chunks: Sequence[Any], *, question: str = "",
) -> Iterator[tuple[re.Match[str], list[int], str]]:
    """Share range/lexical checks between marker validation and passage selection."""
    question_words = _content_words(question) if question else set()
    specific_q_words = question_words - _GENERIC_MATCH_WORDS
    for match, assertion in _cited_assertions(answer):
        indexes = list(dict.fromkeys(int(part) for part in match.group(1).split(",")))
        line_start = answer.rfind("\n", 0, match.start()) + 1
        if not answer[line_start:match.start()].strip():
            remainder = answer[match.end():].split("\n", 1)[0].strip()
            for index in indexes:
                title = getattr(chunks[index - 1], "title", None) if 1 <= index <= len(chunks) else None
                if title and remainder.startswith(f"{title}: "):
                    assertion = remainder[len(title) + 2:]
                    break
        words = _content_words(assertion)
        specific_assertion_words = words - _GENERIC_MATCH_WORDS
        valid = []
        for index in indexes:
            if not 1 <= index <= len(chunks):
                continue
            content = getattr(chunks[index - 1], "content", str(chunks[index - 1]))
            content_words = _content_words(content)

            # If specific question terms exist, but neither the question nor the assertion matches the chunk,
            # this chunk is completely irrelevant to the cited claim.
            if specific_q_words and not (specific_q_words & content_words) and not (specific_assertion_words & content_words):
                continue

            has_assertion_match = bool(words & content_words)
            literals = re.findall(r"`([^`\n]+)`", assertion)
            has_literal_match = any(lit.casefold() in content.casefold() for lit in literals if len(lit) > 1)
            has_specific_q_match = bool(specific_q_words and (specific_q_words & content_words))

            if has_assertion_match or has_literal_match or has_specific_q_match or len(words) < 3:
                valid.append(index)
        yield match, valid, assertion


def verify_citations(
    answer: str, chunks: Sequence[Any], *, question: str = "",
) -> tuple[str, list[int]]:
    """Remove invalid source markers using range checks and a lexical guard.

    This guard does not prove semantic entailment or validate generated facts.
    Code and math formatting are preserved.
    """
    verified = {match.start(): valid for match, valid, _ in _verified_citations(answer, chunks, question=question)}

    def replace(match: re.Match[str]) -> str:
        valid = verified.get(match.start())
        if valid is None:
            return match.group(0)
        return f"[{', '.join(map(str, valid))}]" if valid else ""

    return _MARKER_PATTERN.sub(replace, answer), sorted({i for ids in verified.values() for i in ids})


def _chunk_section_path(meta: Any) -> str:
    """Extract or reconstruct section hierarchy path from chunk metadata."""
    if not isinstance(meta, dict):
        return ""
    if path := meta.get("section_path"):
        return str(path)
    headers = [
        str(meta.get(f"Header {i}"))
        for i in range(1, 7)
        if meta.get(f"Header {i}")
    ]
    return " > ".join(headers)


def extract_cited_passages(
    answer: str, chunks: Sequence[Any], *, question: str = "",
) -> dict[int, tuple[str, ...]]:
    """Keep complete items or a retrieved same-page section under its original markers."""
    passages: dict[int, list[str]] = {}
    overview_words = {
        "what", "which", "list", "all", "summarize", "summarise", "overview",
        "give", "provide", "explain", "describe", "about", "please",
        "compare", "comparison", "difference", "vs", "versus", "contrast",
        "trade-off", "tradeoff", "differentiate", "distinguish",
        "tell", "me", "some", "key",
        "nhung", "cac", "la", "gi", "cho", "biet", "liet", "ke", "uu", "diem",
        "nhuoc", "loi", "ich", "ung", "dung", "tong", "quan", "toan", "bo",
        "so", "sanh", "khac", "nhau", "doi", "chieu", "phan", "loai", "tieu", "chi",
    }
    for _match, valid, assertion in _verified_citations(answer, chunks, question=question):
        for index in valid:
            selected = passages.setdefault(index, [])
            chunk = chunks[index - 1]
            section = _chunk_section_path(chunk.metadata)
            heading_words = _section_terms(section.rsplit(" > ", 1)[-1])
            labels = [
                _section_terms(label)
                for member in chunks
                if _chunk_section_path(member.metadata) == section
                for label in re.findall(r"(?m)^[ \t]*[-+*][ \t]+\*\*([^*]+)\*\*", member.content)
            ]
            overview = any(
                bool(heading_words)
                and (heading_words <= question_words or bool(heading_words & question_words))
                and (question_words - heading_words <= overview_words)
                and not any(label and label <= question_words for label in labels)
                for line in question.splitlines()
                if (question_words := _section_terms(line))
            )
            members = [chunk]
            if overview and section:
                same_section_members = sorted(
                    (
                        member for member in chunks
                        if member.document_id == chunk.document_id
                        and _chunk_section_path(member.metadata) == section
                    ),
                    key=lambda member: (getattr(member, "metadata", None) or {}).get("chunk_index", 0),
                )
                if same_section_members:
                    members = same_section_members

            for member in members:
                if overview:
                    items = [
                        item.strip()
                        for item in re.split(r"(?m)(?=^[ \t]*[-+*]|\d+[.)])|\n\n+", member.content)
                        if item.strip()
                    ]
                    candidates = [
                        item for item in items
                        if not is_ignorable_passage(item, chunk=member, current_section=section)
                    ] if len(items) > 1 else [member.content]
                else:
                    protected, blocks = _protect(assertion)
                    targets = [assertion] if assertion.startswith(("```", "~~~")) else [
                        _restore(part, blocks)
                        for part in re.split(r"(?<=[.!?])\s+|\n+", protected)
                        if part.strip()
                    ]
                    candidates = [
                        extract_best_sentence(member.content, target, question=question)
                        for target in targets
                    ]
                for passage in candidates:
                    if (
                        passage
                        and not is_ignorable_passage(passage, chunk=member, current_section=section)
                        and passage not in selected
                    ):
                        selected.append(passage)
    return {index: tuple(selected) for index, selected in passages.items()}

