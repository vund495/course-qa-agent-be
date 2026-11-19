"""Grounding and length checks for generated quiz items (AI-200).

The generation prompt asks the model to stay inside the supplied material and to
keep every item the same length, but prompt text alone cannot enforce either.
This module is the deterministic layer that runs on the parsed LLM output before
anything reaches the question bank:

* :func:`check_grounding` rejects an item whose ``source_reference`` does not
  appear in the material that was actually sent to the model.
* :func:`measure_lengths` reports the stem and option length spread so the
  prompt change can be judged before and after.

Both functions are pure: no database, no LLM, no network.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Kept in sync with rule 8 of the generation prompt. The prompt states the range
# the model should aim for; these constants are what the check enforces.
STEM_MIN_CHARS = 60
STEM_MAX_CHARS = 160
OPTION_MIN_CHARS = 15
OPTION_MAX_CHARS = 70

# A reference is matched on its normalised text, so "Unit 3: Loops" in the
# material also accepts "unit 3 loops" from the model.
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
_WHITESPACE = re.compile(r"\s+", re.UNICODE)

# A correct option may be a little longer than the distractors without giving
# the answer away; beyond this many extra characters it is flagged as a cue.
ANSWER_CUE_TOLERANCE = 12


def _normalise(text: str) -> str:
    """Fold case, punctuation and whitespace so references compare reliably."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    stripped = _NON_WORD.sub(" ", folded)
    return _WHITESPACE.sub(" ", stripped).strip()


@dataclass(frozen=True)
class GroundingResult:
    """Outcome of checking one generated item against the supplied material."""

    grounded: bool
    reason: str | None = None


def check_grounding(item: dict[str, Any], material: str) -> GroundingResult:
    """Return whether ``item``'s ``source_reference`` exists in ``material``.

    An empty or missing reference is ungrounded: the prompt requires one, and a
    missing reference means the model did not tie the item to any section.
    """
    reference = item.get("source_reference")
    if not isinstance(reference, str) or not reference.strip():
        return GroundingResult(False, "missing source_reference")

    normalised_material = _normalise(material)
    if not normalised_material:
        return GroundingResult(False, "no material supplied to match against")

    normalised_reference = _normalise(reference)
    if not normalised_reference:
        return GroundingResult(False, "source_reference has no matchable text")

    if normalised_reference in normalised_material:
        return GroundingResult(True)

    return GroundingResult(
        False,
        f"source_reference {reference!r} does not appear in the supplied material",
    )


@dataclass
class LengthReport:
    """Stem and option length spread for one generated batch."""

    stem_lengths: list[int] = field(default_factory=list)
    option_lengths: list[int] = field(default_factory=list)
    out_of_range: list[str] = field(default_factory=list)
    answer_cue: list[str] = field(default_factory=list)

    @property
    def stem_spread(self) -> int:
        return _spread(self.stem_lengths)

    @property
    def option_spread(self) -> int:
        return _spread(self.option_lengths)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stem_min": min(self.stem_lengths) if self.stem_lengths else 0,
            "stem_max": max(self.stem_lengths) if self.stem_lengths else 0,
            "stem_spread": self.stem_spread,
            "option_min": min(self.option_lengths) if self.option_lengths else 0,
            "option_max": max(self.option_lengths) if self.option_lengths else 0,
            "option_spread": self.option_spread,
            "out_of_range": list(self.out_of_range),
            "answer_cue": list(self.answer_cue),
        }


def _spread(values: list[int]) -> int:
    return max(values) - min(values) if values else 0


def measure_lengths(items: list[dict[str, Any]]) -> LengthReport:
    """Measure every stem and option, recording which items fall outside range."""
    report = LengthReport()
    for index, item in enumerate(items):
        stem = item.get("question")
        if isinstance(stem, str):
            length = len(stem.strip())
            report.stem_lengths.append(length)
            if not STEM_MIN_CHARS <= length <= STEM_MAX_CHARS:
                report.out_of_range.append(
                    f"item {index}: stem is {length} chars "
                    f"(expected {STEM_MIN_CHARS}-{STEM_MAX_CHARS})"
                )

        options = item.get("options") or []
        if not isinstance(options, list):
            continue

        option_texts = [
            opt.get("option_text")
            for opt in options
            if isinstance(opt, dict) and isinstance(opt.get("option_text"), str)
        ]
        # An item whose options are all short is a technical-identifier item
        # (`<vector>`, `new`, `//`). Padding those to the prose minimum would make
        # them wrong or meaningless, so the minimum only applies to prose items.
        identifier_item = bool(option_texts) and all(
            len(text.strip()) < OPTION_MIN_CHARS for text in option_texts
        )

        for option in options:
            if not isinstance(option, dict):
                continue
            text = option.get("option_text")
            if not isinstance(text, str):
                continue
            length = len(text.strip())
            report.option_lengths.append(length)
            too_short = length < OPTION_MIN_CHARS and not identifier_item
            if too_short or length > OPTION_MAX_CHARS:
                label = option.get("option_label", "?")
                report.out_of_range.append(
                    f"item {index}: option {label} is {length} chars "
                    f"(expected {OPTION_MIN_CHARS}-{OPTION_MAX_CHARS})"
                )

        report.answer_cue.extend(_answer_cue_warnings(index, options))
    return report


def _answer_cue_warnings(index: int, options: Any) -> list[str]:
    """Flag a correct option that is visibly longer than its distractors.

    A correct answer that is the longest option tells the student which one to
    pick without reading the question. The mentor asked for balanced options, so
    the check reports the gap rather than silently accepting it.
    """
    if not isinstance(options, list):
        return []

    correct: list[int] = []
    wrong: list[int] = []
    for option in options:
        if not isinstance(option, dict):
            continue
        text = option.get("option_text")
        if not isinstance(text, str) or not text.strip():
            continue
        length = len(text.strip())
        if option.get("is_correct"):
            correct.append(length)
        else:
            wrong.append(length)

    if not correct or not wrong:
        return []

    longest_correct = max(correct)
    longest_wrong = max(wrong)
    if longest_correct > longest_wrong + ANSWER_CUE_TOLERANCE:
        return [
            (
                f"item {index}: correct option is {longest_correct} chars but the "
                f"longest distractor is {longest_wrong} chars, which gives the answer away"
            )
        ]
    return []
