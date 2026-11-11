"""Render a cited PDF with the passages used for an answer highlighted."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path

import pymupdf

from app.services.ingestion.chunker import _fenced_ranges
from app.services.ingestion.cleaner import _protect, _restore, _strip_emphasis

_TOKEN_PATTERN = re.compile(r"\w+(?:\.\w+)*|[^\w\s]")


def _norm(word: str) -> str:
    return unicodedata.normalize("NFC", word).replace("\u00ad", "")


def _tokens(text: str) -> list[str]:
    """Normalize source formatting without discarding signs, operators, or identifiers."""
    text = text.strip()
    fences = _fenced_ranges(text)
    if fences:
        tokens: list[str] = []
        cursor = 0
        for start, end in fences:
            tokens.extend(_tokens(text[cursor:start]))
            lines = text[start:end].splitlines()
            opening = re.match(r"`{3,}|~{3,}", lines[0].lstrip())[0]
            body = lines[1:]
            if body and re.fullmatch(rf"{re.escape(opening[0])}{{{len(opening)},}}", body[-1].strip()):
                body.pop()
            tokens.extend(_TOKEN_PATTERN.findall(_norm("\n".join(body))))
            cursor = end
        tokens.extend(_tokens(text[cursor:]))
        return tokens
    text, blocks = _protect(text)
    # PDF extraction adds these formatting tags; they are not visible source text.
    text = re.sub(r"</?(?:u|mark|sup|sub)>", "", text)
    text = re.sub(r"(?m)^[ \t]*(?:#{1,6}[ \t]+|[-+*][ \t]+)", "", text)
    text = _strip_emphasis(text)
    if text.startswith("|") and text.endswith("|"):
        text = " ".join(re.split(r"(?<!\\)\|", text[1:-1])).replace(r"\|", "|")
    text = _restore(text, blocks).replace("`", "")
    return _TOKEN_PATTERN.findall(_norm(text))


def _compute_page_rects(
    page: pymupdf.Page,
    passages: Sequence[str],
) -> list[pymupdf.Rect]:
    """Match each full passage at one unique position, without sentence expansion."""
    if not passages:
        return []

    raw_words = page.get_text("words", sort=False)  # (x0, y0, x1, y1, text, block, line, n)
    if not raw_words:
        return []

    # Preserve natural layout reading order (columns and blocks are ordered by block_no, line_no, word_no)
    words = sorted(raw_words, key=lambda w: (w[5], w[6], w[7]))

    variants: list[tuple[list[str], list[tuple[int, ...]]]] = []
    for dehyphenate in (False, True):
        tokens: list[str] = []
        spans: list[tuple[int, ...]] = []
        index = 0
        while index < len(words):
            text = _norm(words[index][4])
            indexes = (index,)
            if text in {"•", "·", "\uf0b7"} and words[index][7] == 0:
                index += 1
                continue
            if (
                dehyphenate and index + 1 < len(words)
                and len(text) > 1 and text.endswith("-") and text[-2].isalpha()
                and words[index][5] == words[index + 1][5]
                and words[index][6] != words[index + 1][6]
                and words[index + 1][4][0].islower()
            ):
                text = text[:-1] + _norm(words[index + 1][4])
                indexes = (index, index + 1)
                index += 1
            parts = _TOKEN_PATTERN.findall(text)
            tokens.extend(parts)
            spans.extend([indexes] * len(parts))
            index += 1
        variants.append((tokens, spans))

    selected_words: set[int] = set()
    expanded_passages: list[str] = []
    for passage in passages:
        expanded_passages.append(passage)
        # If passage contains bullet points or separate lines, decompose as fallbacks
        items = [
            part.strip()
            for part in re.split(r"(?m)(?=^[ \t]*[-*+]|\d+[.)])|\n\n+", passage)
            if part.strip()
        ]
        if len(items) > 1:
            expanded_passages.extend(items)

    for passage in expanded_passages:
        expected = _tokens(passage)
        if not expected:
            continue
        matches: set[tuple[int, ...]] = set()
        for tokens, spans in variants:
            for start in range(len(tokens) - len(expected) + 1):
                if tokens[start:start + len(expected)] == expected:
                    end = start + len(expected)
                    if (
                        (start > 0 and spans[start - 1] == spans[start])
                        or (end < len(spans) and spans[end - 1] == spans[end])
                    ):
                        continue
                    matches.add(tuple(sorted({
                        index for span in spans[start:end] for index in span
                    })))
        if matches:
            for match in matches:
                selected_words.update(match)
    return [pymupdf.Rect(words[index][:4]) for index in sorted(selected_words)]


def get_highlight_rects(
    path: Path,
    page_number: int,
    passages: Sequence[str],
    pages: Sequence[int] | None = None,
) -> list[dict[str, float]]:
    """Return lightweight bounding boxes [{x0, y0, x1, y1}] without re-rendering entire PDF bytes."""
    doc = pymupdf.open(path)
    try:
        explicit_pages = [p for p in (pages or []) if 1 <= p <= doc.page_count]
        if explicit_pages:
            candidate_pages = list(dict.fromkeys(
                explicit_pages + [p + d for p in explicit_pages for d in (1, -1)]
            ))
        else:
            candidate_pages = [page_number] + [
                page_number + d for d in (1, -1, 2, -2) if 1 <= page_number + d <= doc.page_count
            ]
        seen_pages: set[int] = set()
        for p_num in candidate_pages:
            if 1 <= p_num <= doc.page_count and p_num not in seen_pages:
                seen_pages.add(p_num)
                page = doc[p_num - 1]
                rects = _compute_page_rects(page, passages)
                if rects:
                    return [
                        {"x0": round(r.x0, 2), "y0": round(r.y0, 2), "x1": round(r.x1, 2), "y1": round(r.y1, 2)}
                        for r in rects
                    ]
        return []
    finally:
        doc.close()


def highlight_pdf_with_page(
    path: Path,
    page_number: int,
    passages: Sequence[str],
    pages: Sequence[int] | None = None,
) -> tuple[bytes, int]:
    """Return the PDF with the cited passages highlighted, plus the page number with the most highlights."""
    doc = pymupdf.open(path)
    try:
        explicit_pages = [p for p in (pages or []) if 1 <= p <= doc.page_count]
        if explicit_pages:
            candidate_pages = list(dict.fromkeys(
                explicit_pages + [p + d for p in explicit_pages for d in (1, -1)]
            ))
        else:
            candidate_pages = [page_number] + [
                page_number + d for d in (1, -1, 2, -2) if 1 <= page_number + d <= doc.page_count
            ]
        seen_pages: set[int] = set()
        page_rect_counts: dict[int, int] = {}
        for p_num in candidate_pages:
            if 1 <= p_num <= doc.page_count and p_num not in seen_pages:
                seen_pages.add(p_num)
                page = doc[p_num - 1]
                rects = _compute_page_rects(page, passages)
                if rects:
                    page_rect_counts[p_num] = len(rects)
                    annotation = page.add_highlight_annot(quads=[rect.quad for rect in rects])
                    annotation.set_colors(stroke=(1, 0.85, 0.2))
                    annotation.update()
        if page_rect_counts:
            forward_pages = [p for p in page_rect_counts if p >= page_number]
            best_page = min(forward_pages) if forward_pages else min(page_rect_counts, key=lambda p: abs(p - page_number))
        else:
            best_page = page_number
        return doc.tobytes(garbage=3, deflate=True), best_page
    finally:
        doc.close()


def highlight_pdf(path: Path, page_number: int, passages: Sequence[str], pages: Sequence[int] | None = None) -> bytes:
    """Return the PDF with the cited passages highlighted on ``page_number`` and adjacent pages."""
    content, _ = highlight_pdf_with_page(path, page_number, passages, pages=pages)
    return content
