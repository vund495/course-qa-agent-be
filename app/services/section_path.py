"""Clean section-path metadata for citations and retrieval continuity."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# OCR picture text can be promoted to a Markdown heading and then inherited as
# a parent section across pages. The observed Dsa artifact uses lowercase <br>
# tags and an HTML comment ("<!-- End of picture text -->"). Keep detection
# narrow so valid headings such as "OCR Overview", "Picture Text" or
# "Stack <p>" survive.
_OCR_BR_TAG = r"</?br(?:\s[^<>]*)?/?>"
_CORRUPTED_SECTION_MARKER = re.compile(rf"{_OCR_BR_TAG}|<!--|-->")


def is_corrupted_section_segment(value: Any) -> bool:
    """Return True when a section label is OCR/picture markup, not a heading."""

    text = str(value or "").strip()
    return bool(text and _CORRUPTED_SECTION_MARKER.search(text))


def clean_section_path(path: Any) -> str:
    """Drop corrupted segments while preserving the valid nested hierarchy."""

    text = str(path or "").strip()
    if not text:
        return ""
    segments = [segment.strip() for segment in text.split(" > ")]
    return " > ".join(
        segment
        for segment in segments
        if segment and not is_corrupted_section_segment(segment)
    )


def section_path_from_metadata(meta: Mapping[str, Any] | None) -> str:
    """Prefer a cleaned stored path, then reconstruct a cleaned header path."""

    if not isinstance(meta, Mapping):
        return ""
    headers = [
        str(meta.get(f"Header {index}"))
        for index in range(1, 7)
        if meta.get(f"Header {index}")
    ]
    headers_path = clean_section_path(" > ".join(headers))
    path = clean_section_path(meta.get("section_path"))
    if any(is_corrupted_section_segment(header) for header in headers):
        # A corrupted header proves the stored path may still carry the stale
        # OCR prefix; the cleaned header hierarchy is the safer citation source.
        return headers_path or path
    return path or headers_path
