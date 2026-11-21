"""Opaque keyset cursors for list endpoints (AI-185).

A cursor records the sort position of the last row a client received, so the
next page resumes with an index seek instead of an ``OFFSET`` scan. The payload
is base64url-encoded JSON and is deliberately opaque: clients echo
``next_cursor`` back verbatim and never build one themselves.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import UTC, datetime

CURSOR_VERSION = 1

# A well-formed cursor is ~150 characters. Anything far longer is not ours.
MAX_CURSOR_LENGTH = 512


class InvalidCursorError(ValueError):
    """Raised when a cursor is malformed or belongs to another section."""


def encode_cursor(section: str, timestamp: datetime, row_id: uuid.UUID) -> str:
    """Encode a keyset position as an opaque, URL-safe string.

    SQLite drops ``tzinfo`` on read, so a naive value is treated as UTC. The
    application stores every timestamp in UTC, which makes that assumption safe
    and keeps the payload timezone-aware on both backends.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    payload = {
        "v": CURSOR_VERSION,
        "s": section,
        "t": timestamp.isoformat(),
        "id": str(row_id),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(raw: str, expected_section: str) -> tuple[datetime, uuid.UUID]:
    """Decode a cursor, rejecting malformed payloads and section mismatches."""
    if not raw or len(raw) > MAX_CURSOR_LENGTH:
        raise InvalidCursorError("Malformed cursor.")

    try:
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursorError("Malformed cursor.") from exc

    if not isinstance(payload, dict):
        raise InvalidCursorError("Malformed cursor.")
    if payload.get("v") != CURSOR_VERSION:
        raise InvalidCursorError("Unsupported cursor version.")
    if payload.get("s") != expected_section:
        raise InvalidCursorError("Cursor does not belong to this section.")

    raw_timestamp = payload.get("t")
    raw_id = payload.get("id")
    if not isinstance(raw_timestamp, str) or not isinstance(raw_id, str):
        raise InvalidCursorError("Malformed cursor payload.")

    try:
        timestamp = datetime.fromisoformat(raw_timestamp)
        row_id = uuid.UUID(raw_id)
    except ValueError as exc:
        raise InvalidCursorError("Malformed cursor payload.") from exc

    # The sort columns are timestamptz; a naive timestamp would compare wrong.
    if timestamp.tzinfo is None:
        raise InvalidCursorError("Malformed cursor payload.")

    return timestamp, row_id
