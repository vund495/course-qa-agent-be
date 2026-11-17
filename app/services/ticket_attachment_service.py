"""Image and emoji attachments for ticket replies (AI-89 follow-up media)."""

from __future__ import annotations

import io
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config.config import settings
from app.models.ticket import Ticket, TicketAttachment, TicketReply

logger = logging.getLogger(__name__)

# Product limits: a single follow-up carries at most three visuals, and each
# image stays small enough for a phone screenshot or photo.
MAX_ATTACHMENTS_PER_REPLY = 3
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_EMOJI_LENGTH = 16
# Pending uploads that never became a reply are dropped after this window.
ORPHAN_TTL = timedelta(hours=24)

# Pillow format -> served MIME type. The client-declared content type is never
# trusted; the actual decoded image format decides.
IMAGE_MIME_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}
IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class AttachmentError(ValueError):
    """A user-facing attachment validation failure."""


def pending_count(db: Session, *, ticket_id: uuid.UUID, user_id: uuid.UUID) -> int:
    """Attachments uploaded by this user for this ticket but not sent yet."""
    return (
        db.query(TicketAttachment)
        .filter(
            TicketAttachment.ticket_id == ticket_id,
            TicketAttachment.uploaded_by == user_id,
            TicketAttachment.reply_id.is_(None),
        )
        .count()
    )


def purge_orphans(db: Session, *, ticket_id: uuid.UUID) -> None:
    """Remove unsent attachments older than ORPHAN_TTL for one ticket."""
    cutoff = datetime.now(UTC) - ORPHAN_TTL
    stale = (
        db.query(TicketAttachment)
        .filter(
            TicketAttachment.ticket_id == ticket_id,
            TicketAttachment.reply_id.is_(None),
            TicketAttachment.created_at < cutoff,
        )
        .all()
    )
    if not stale:
        return
    for record in stale:
        _unlink(record)
        db.delete(record)
    db.commit()


def save_images(
    db: Session,
    *,
    ticket: Ticket,
    user_id: uuid.UUID,
    uploads: list[tuple[str, bytes]],
) -> list[TicketAttachment]:
    """Validate and persist image uploads, returning unbound attachments."""
    if not uploads:
        return []
    cleaned: list[tuple[str, str, bytes, int]] = []
    for raw_name, content in uploads:
        if not content:
            raise AttachmentError(f"{raw_name or 'Image'} is empty.")
        if len(content) > MAX_IMAGE_BYTES:
            raise AttachmentError(
                f"{raw_name or 'Image'} is larger than 5 MB; please compress it first."
            )
        mime_type = _detect_image_mime(content, raw_name)
        cleaned.append((raw_name or "image", mime_type, content, len(content)))

    _ensure_capacity(db, ticket=ticket, user_id=user_id, incoming=len(cleaned))

    storage_dir = settings.ticket_storage_dir.resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)

    created: list[TicketAttachment] = []
    for raw_name, mime_type, content, size in cleaned:
        attachment_id = uuid.uuid4()
        extension = IMAGE_EXTENSIONS.get(mime_type, ".bin")
        path = storage_dir / f"{attachment_id}{extension}"
        try:
            path.write_bytes(content)
        except OSError:
            path.unlink(missing_ok=True)
            raise AttachmentError("Could not store the image; please try again.") from None
        record = TicketAttachment(
            id=attachment_id,
            ticket_id=ticket.id,
            uploaded_by=user_id,
            kind="IMAGE",
            file_name=_safe_name(raw_name),
            mime_type=mime_type,
            size_bytes=size,
            # File name only: the same row must resolve on the host (D:\...) and
            # inside the Docker image (/app/storage/...), so no absolute path is
            # persisted. settings.ticket_storage_dir is the single root.
            storage_path=path.name,
        )
        db.add(record)
        created.append(record)
    db.commit()
    for record in created:
        db.refresh(record)
    return created


def save_emojis(
    db: Session,
    *,
    ticket: Ticket,
    user_id: uuid.UUID,
    emojis: list[str],
) -> list[TicketAttachment]:
    """Store emoji attachments; they need no file on disk."""
    cleaned: list[str] = []
    for value in emojis:
        emoji = (value or "").strip()
        if not emoji:
            continue
        if len(emoji) > MAX_EMOJI_LENGTH:
            raise AttachmentError("That emoji is too long.")
        if any(ord(char) < 32 for char in emoji):
            raise AttachmentError("That emoji is not valid.")
        cleaned.append(emoji)
    if not cleaned:
        return []

    _ensure_capacity(db, ticket=ticket, user_id=user_id, incoming=len(cleaned))

    created = [
        TicketAttachment(
            ticket_id=ticket.id,
            uploaded_by=user_id,
            kind="EMOJI",
            emoji=emoji,
        )
        for emoji in cleaned
    ]
    db.add_all(created)
    db.commit()
    for record in created:
        db.refresh(record)
    return created


def validate_bindable(
    db: Session,
    *,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
    attachment_ids: list[uuid.UUID],
) -> None:
    """Fail before the reply is created so a bad id cannot leave a half state."""
    if not attachment_ids:
        return
    wanted = list(dict.fromkeys(attachment_ids))
    if len(wanted) > MAX_ATTACHMENTS_PER_REPLY:
        raise AttachmentError(
            f"A message can carry at most {MAX_ATTACHMENTS_PER_REPLY} attachments."
        )
    records = (
        db.query(TicketAttachment)
        .filter(
            TicketAttachment.id.in_(wanted),
            TicketAttachment.ticket_id == ticket_id,
            TicketAttachment.reply_id.is_(None),
            TicketAttachment.uploaded_by == user_id,
        )
        .count()
    )
    if records != len(wanted):
        raise AttachmentError("Some attachments are no longer available; please re-add them.")


def bind_to_reply(
    db: Session,
    *,
    reply: TicketReply,
    attachment_ids: list[uuid.UUID],
) -> None:
    """Attach pending uploads to the reply that just sent them."""
    if not attachment_ids:
        return
    validate_bindable(
        db,
        ticket_id=reply.ticket_id,
        user_id=reply.user_id,
        attachment_ids=attachment_ids,
    )
    wanted = list(dict.fromkeys(attachment_ids))
    records = (
        db.query(TicketAttachment)
        .filter(
            TicketAttachment.id.in_(wanted),
            TicketAttachment.ticket_id == reply.ticket_id,
            TicketAttachment.reply_id.is_(None),
            TicketAttachment.uploaded_by == reply.user_id,
        )
        .all()
    )
    for record in records:
        record.reply_id = reply.id
    db.commit()
    db.refresh(reply)


def delete_pending(db: Session, *, attachment_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Delete an unsent attachment owned by the caller."""
    record = db.query(TicketAttachment).filter(TicketAttachment.id == attachment_id).first()
    if record is None or record.reply_id is not None or record.uploaded_by != user_id:
        return False
    _unlink(record)
    db.delete(record)
    db.commit()
    return True


def image_path(record: TicketAttachment) -> Path | None:
    """Resolve the stored file, refusing paths outside the ticket storage root."""
    if record.kind != "IMAGE" or not record.storage_path:
        return None
    root = settings.ticket_storage_dir.resolve()
    stored = Path(record.storage_path)
    # Rows written before this was relative, or by another environment, carry an
    # absolute path (/app/storage/... in Docker, D:\... on a host run). Only the
    # file name is portable, so the in-root copy is tried as a fallback. Both
    # candidates still have to land inside the root.
    candidates = [stored, root / stored.name]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    logger.warning("Ticket attachment %s is missing under %s", record.id, root)
    return None


def _ensure_capacity(db: Session, *, ticket: Ticket, user_id: uuid.UUID, incoming: int) -> None:
    purge_orphans(db, ticket_id=ticket.id)
    current = pending_count(db, ticket_id=ticket.id, user_id=user_id)
    if current + incoming > MAX_ATTACHMENTS_PER_REPLY:
        raise AttachmentError(
            f"A message can carry at most {MAX_ATTACHMENTS_PER_REPLY} images and emojis."
        )


def _detect_image_mime(content: bytes, raw_name: str) -> str:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image_format = (image.format or "").upper()
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise AttachmentError(f"{raw_name or 'That file'} is not a valid image.") from None
    mime_type = IMAGE_MIME_TYPES.get(image_format)
    if mime_type is None:
        raise AttachmentError("Only PNG, JPEG, WEBP and GIF images are supported.")
    return mime_type


def _safe_name(raw_name: str) -> str:
    cleaned = Path(raw_name or "image").name.strip()
    return cleaned[:255] or "image"


def _unlink(record: TicketAttachment) -> None:
    path = image_path(record)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove ticket attachment file %s", path, exc_info=True)
