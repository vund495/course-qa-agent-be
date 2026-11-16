"""Tests for the AI-200 grounding and length checks on generated quiz items."""

from __future__ import annotations

import pytest

from app.services.question_grounding import (
    OPTION_MAX_CHARS,
    OPTION_MIN_CHARS,
    STEM_MAX_CHARS,
    STEM_MIN_CHARS,
    check_grounding,
    measure_lengths,
)

MATERIAL = """
Document 'week3-loops.pdf':
Unit 3: Iteration and Loops
A for loop repeats a block a fixed number of times. A while loop repeats while
its condition stays true. The break statement exits the innermost loop early.
"""


def _item(**overrides):
    item = {
        "skill_code": "LOOPS",
        "question_type": "SINGLE_CHOICE",
        "difficulty": "NOVICE",
        "question": "Which statement exits the innermost loop before its condition becomes false?",
        "options": [
            {"option_label": "A", "option_text": "The break statement", "is_correct": True},
            {"option_label": "B", "option_text": "The continue statement", "is_correct": False},
            {"option_label": "C", "option_text": "The return statement", "is_correct": False},
            {"option_label": "D", "option_text": "The pass statement", "is_correct": False},
        ],
        "source_reference": "Unit 3: Iteration and Loops",
    }
    item.update(overrides)
    return item


def test_grounded_item_passes():
    result = check_grounding(_item(), MATERIAL)
    assert result.grounded is True
    assert result.reason is None


def test_unmatched_source_reference_is_rejected():
    item = _item(source_reference="Chapter 9: Recursion and Backtracking")
    result = check_grounding(item, MATERIAL)
    assert result.grounded is False
    assert "does not appear in the supplied material" in result.reason


def test_missing_source_reference_is_rejected():
    item = _item()
    del item["source_reference"]
    result = check_grounding(item, MATERIAL)
    assert result.grounded is False
    assert result.reason == "missing source_reference"


def test_reference_matches_ignoring_case_and_punctuation():
    item = _item(source_reference="unit 3 iteration and loops")
    assert check_grounding(item, MATERIAL).grounded is True


def test_empty_material_rejects_everything():
    result = check_grounding(_item(), "   ")
    assert result.grounded is False


def test_well_formed_item_is_within_length_range():
    report = measure_lengths([_item()])
    assert report.out_of_range == []
    assert STEM_MIN_CHARS <= report.stem_lengths[0] <= STEM_MAX_CHARS
    for length in report.option_lengths:
        assert OPTION_MIN_CHARS <= length <= OPTION_MAX_CHARS


def test_item_outside_length_range_is_flagged():
    long_stem = "Why " + ("does this loop keep running forever " * 8) + "?"
    report = measure_lengths([_item(question=long_stem)])
    assert report.out_of_range
    assert "stem is" in report.out_of_range[0]


def test_option_outside_length_range_is_flagged():
    item = _item(
        options=[
            {
                "option_label": "A",
                "option_text": (
                    "The break statement, which exits the innermost loop early "
                    "before its condition becomes false"
                ),
                "is_correct": True,
            },
            {"option_label": "B", "option_text": "The continue statement", "is_correct": False},
        ]
    )
    report = measure_lengths([item])
    assert any("option A is" in entry for entry in report.out_of_range)


def test_length_report_records_spread():
    short = _item(question="Which statement exits a loop early?")
    long = _item(
        question="Which statement exits the innermost loop before its condition becomes false?"
    )
    report = measure_lengths([short, long])
    assert report.stem_spread == max(report.stem_lengths) - min(report.stem_lengths)
    assert report.stem_spread > 0
    assert report.as_dict()["stem_spread"] == report.stem_spread


@pytest.mark.parametrize("bad", [None, 42, {}])
def test_non_string_stem_is_ignored(bad):
    report = measure_lengths([_item(question=bad)])
    assert report.stem_lengths == []


def test_correct_option_longer_than_distractors_is_flagged():
    item = _item(
        options=[
            {
                "option_label": "A",
                "option_text": "The break statement, which exits the innermost loop early",
                "is_correct": True,
            },
            {"option_label": "B", "option_text": "The continue statement", "is_correct": False},
            {"option_label": "C", "option_text": "The return statement", "is_correct": False},
            {"option_label": "D", "option_text": "The pass statement", "is_correct": False},
        ]
    )
    report = measure_lengths([item])
    assert report.answer_cue
    assert "gives the answer away" in report.answer_cue[0]


def test_balanced_options_produce_no_answer_cue():
    report = measure_lengths([_item()])
    assert report.answer_cue == []


def test_technical_identifier_options_are_not_flagged_as_too_short():
    item = _item(
        options=[
            {"option_label": "A", "option_text": "<array>", "is_correct": True},
            {"option_label": "B", "option_text": "<bitset>", "is_correct": True},
            {"option_label": "C", "option_text": "<vector>", "is_correct": False},
            {"option_label": "D", "option_text": "<deque>", "is_correct": True},
        ]
    )
    report = measure_lengths([item])
    assert report.out_of_range == []


def test_one_short_option_among_prose_options_is_still_flagged():
    item = _item(
        options=[
            {"option_label": "A", "option_text": "new", "is_correct": True},
            {"option_label": "B", "option_text": "malloc and free", "is_correct": False},
            {"option_label": "C", "option_text": "alloc and dealloc", "is_correct": False},
            {"option_label": "D", "option_text": "get and release", "is_correct": False},
        ]
    )
    report = measure_lengths([item])
    assert any("option A is" in entry for entry in report.out_of_range)
