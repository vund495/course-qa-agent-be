"""Minimal index for consumed web-consent links.

The index is built from column-only consent rows so history and Content Gap
never load offer text, question text or JSON payloads just to verify a link.
A web answer is consumed only when the same consent row carries both the course
assistant message ID and the web assistant message ID.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConsentIndex:
    """Consumed pairs plus the IDs that have any consent row at all."""

    consumed_pairs: frozenset[tuple[uuid.UUID, uuid.UUID]] = frozenset()
    web_ids: frozenset[uuid.UUID] = frozenset()
    course_ids: frozenset[uuid.UUID] = frozenset()

    def is_consumed(self, course_id: uuid.UUID, web_id: uuid.UUID) -> bool:
        return (course_id, web_id) in self.consumed_pairs

    def web_has_consent(self, web_id: uuid.UUID) -> bool:
        return web_id in self.web_ids

    def course_has_consent(self, course_id: uuid.UUID) -> bool:
        return course_id in self.course_ids


EMPTY_CONSENT_INDEX = ConsentIndex()


def build_consent_index(rows: Iterable[Any]) -> ConsentIndex:
    """Build one index from rows exposing the three consent metadata fields."""

    consumed: set[tuple[uuid.UUID, uuid.UUID]] = set()
    web_ids: set[uuid.UUID] = set()
    course_ids: set[uuid.UUID] = set()
    for row in rows:
        course_id = getattr(row, "assistant_message_id", None)
        web_id = getattr(row, "web_message_id", None)
        status = getattr(row, "status", None)
        if course_id is not None:
            course_ids.add(course_id)
        if web_id is not None:
            web_ids.add(web_id)
        if status == "consumed" and course_id is not None and web_id is not None:
            consumed.add((course_id, web_id))
    return ConsentIndex(
        consumed_pairs=frozenset(consumed),
        web_ids=frozenset(web_ids),
        course_ids=frozenset(course_ids),
    )
