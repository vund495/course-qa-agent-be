"""PDF highlighting for cited passages."""

from __future__ import annotations

import pymupdf

from app.services.pdf_highlight_service import (
    get_highlight_rects,
    highlight_pdf,
    highlight_pdf_with_page,
)


def _make_pdf(path) -> None:
    doc = pymupdf.open()
    page_one = doc.new_page()
    page_one.insert_text((72, 72), "Introduction to the course syllabus.")
    page_two = doc.new_page()
    page_two.insert_text((72, 72), "Water evaporates then condenses into clouds.")
    page_two.insert_text((72, 120), "Unrelated closing remark about grading.")
    doc.save(path)
    doc.close()


def _highlight_count(pdf_bytes: bytes, page_index: int) -> int:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return len(list(doc[page_index].annots() or []))
    finally:
        doc.close()


def test_highlights_only_the_cited_passage_on_the_cited_page(tmp_path) -> None:
    source = tmp_path / "lesson.pdf"
    _make_pdf(source)

    result = highlight_pdf(source, 2, ["**Water** evaporates then condenses into clouds."])

    assert _highlight_count(result, 1) == 1
    assert _highlight_count(result, 0) == 0


def test_no_highlight_when_passage_is_not_on_the_page(tmp_path) -> None:
    source = tmp_path / "lesson.pdf"
    _make_pdf(source)

    result = highlight_pdf(source, 1, ["Water evaporates then condenses into clouds."])

    assert _highlight_count(result, 0) == 0


def test_out_of_range_page_returns_the_pdf_unchanged(tmp_path) -> None:
    source = tmp_path / "lesson.pdf"
    _make_pdf(source)

    assert highlight_pdf(source, 99, ["anything here at all"]).startswith(b"%PDF")


def test_get_highlight_rects_returns_coordinates(tmp_path) -> None:
    source = tmp_path / "lesson.pdf"
    _make_pdf(source)

    rects = get_highlight_rects(source, 2, ["Water evaporates then condenses into clouds."])
    assert len(rects) > 0
    first = rects[0]
    assert "x0" in first and "y0" in first and "x1" in first and "y1" in first
    assert first["x1"] > first["x0"]
    assert first["y1"] > first["y0"]


def test_filters_isolated_three_word_random_matches(tmp_path) -> None:
    source = tmp_path / "isolated.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    # Line 1: has common 3 words "is used to"
    page.insert_text((72, 72), "This device is used to measure temperature.")
    # Line 2: completely separate topic
    page.insert_text((72, 140), "Quantum mechanics governs particle behavior at nanoscale.")
    doc.save(source)
    doc.close()

    # Passage is about quantum mechanics, and happens to end with "is used to describe"
    passage = "Quantum mechanics governs particle behavior at nanoscale and is used to describe atoms."
    rects = get_highlight_rects(source, 1, [passage])
    # A matching prefix cannot justify highlighting a quote absent from the page.
    assert rects == []


def test_highlights_two_column_pdf_passage(tmp_path) -> None:
    source = tmp_path / "twocol.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    # Column 1 (left)
    page.insert_text((50, 50), "Programs consist of statements")
    page.insert_text((50, 70), "to be run in sequence.")
    # Column 2 (right) at the same vertical positions
    page.insert_text((300, 50), "A statement describes some")
    page.insert_text((300, 70), "action to be carried out.")
    doc.save(source)
    doc.close()

    # Column 1 passage
    passage_col1 = "Programs consist of statements to be run in sequence."
    rects_col1 = get_highlight_rects(source, 1, [passage_col1])
    assert len(rects_col1) > 0

    # Column 2 passage
    passage_col2 = "A statement describes some action to be carried out."
    rects_col2 = get_highlight_rects(source, 1, [passage_col2])
    assert len(rects_col2) > 0


def test_highlights_repeated_sentences_on_same_page(tmp_path) -> None:
    source = tmp_path / "repeated.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    sentence = "Important theorem: Every closed graph is complete."
    page.insert_text((72, 72), sentence)
    page.insert_text((72, 200), "Intermediate discussions and calculations.")
    # Repeated at the bottom summary
    page.insert_text((72, 350), sentence)
    doc.save(source)
    doc.close()

    rects = get_highlight_rects(source, 1, [sentence])
    # Both occurrences should produce rects
    assert len(rects) >= 2


def test_highlights_cross_page_and_adjacent_offsets(tmp_path) -> None:
    source = tmp_path / "cross_page.pdf"
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Advantage 1: Rich Standard Library STL.")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Advantage 2: OOPS Concepts and Abstraction.")
    doc.save(source)
    doc.close()

    # Passages span across page 1 and page 2
    passages = [
        "Advantage 1: Rich Standard Library STL.",
        "Advantage 2: OOPS Concepts and Abstraction.",
    ]
    result = highlight_pdf(source, 1, passages)
    # Both page 1 (idx 0) and page 2 (idx 1) are annotated
    assert _highlight_count(result, 0) == 1
    assert _highlight_count(result, 1) == 1


def test_highlight_pdf_with_page_returns_page_with_most_highlights(tmp_path) -> None:
    source = tmp_path / "page_counts.pdf"
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Section title.")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Advantage 1: Rich Standard Library STL.")
    p2.insert_text((72, 120), "Advantage 2: OOPS Concepts and Abstraction.")
    doc.save(source)
    doc.close()

    passages = [
        "Advantage 1: Rich Standard Library STL.",
        "Advantage 2: OOPS Concepts and Abstraction.",
    ]
    # Page 1 is cited, but points are located on page 2
    content, best_page = highlight_pdf_with_page(source, 1, passages)
    assert best_page == 2
    assert _highlight_count(content, 1) == 1


def test_highlight_pdf_with_page_supports_explicit_pages_across_range(tmp_path) -> None:
    source = tmp_path / "explicit_pages.pdf"
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Advantage 1: Rich Standard Library STL.")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Advantage 2: OOPS Concepts and Abstraction.")
    doc.save(source)
    doc.close()

    passages = [
        "Advantage 1: Rich Standard Library STL.",
        "Advantage 2: OOPS Concepts and Abstraction.",
    ]
    content, best_page = highlight_pdf_with_page(source, 1, passages, pages=[1, 2])
    assert best_page == 1
    assert _highlight_count(content, 0) == 1
    assert _highlight_count(content, 1) == 1

