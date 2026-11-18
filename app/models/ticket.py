"""Student-created tickets and their replies (AI-81)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.attendance import TicketHandover
    from app.models.user import User


class Ticket(Base):
    __tablename__ = "ticket"
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'ANSWERED', 'RESOLVED', 'EXPIRED')",
            name="ck_ticket_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("class.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    original_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("chat_message.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OPEN", server_default="OPEN"
    )
    # Starts a fresh expiration window when a resolved ticket is reopened.
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    escalated_to_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    student_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_trainer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    queued_for_admin_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    replies: Mapped[list["TicketReply"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketReply.created_at",
    )
    attachments: Mapped[list["TicketAttachment"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketAttachment.created_at",
    )
    # Joined so a ticket list does not issue one SELECT per escalated ticket.
    escalated_to: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[escalated_to_id], lazy="joined"
    )
    owner: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[owner_trainer_id], lazy="joined"
    )
    handovers: Mapped[list["TicketHandover"]] = relationship(
        "TicketHandover",
        back_populates="ticket",
        order_by="TicketHandover.created_at.desc()",
        lazy="selectin",
    )

    @property
    def escalated_to_name(self) -> str | None:
        return self.escalated_to.full_name if self.escalated_to is not None else None

    @property
    def owner_trainer_name(self) -> str | None:
        return self.owner.full_name if self.owner is not None else None

    def _latest_accepted_handover(self) -> Optional["TicketHandover"]:
        for handover in self.handovers:
            if handover.status == "accepted":
                return handover
        return None

    @property
    def handover_from_id(self) -> uuid.UUID | None:
        handover = self._latest_accepted_handover()
        return handover.from_trainer_id if handover is not None else None

    @property
    def handover_from_name(self) -> str | None:
        handover = self._latest_accepted_handover()
        return handover.from_trainer_name if handover is not None else None

    @property
    def handover_reason(self) -> str | None:
        handover = self._latest_accepted_handover()
        return handover.reason if handover is not None else None

    @property
    def handover_at(self) -> datetime | None:
        handover = self._latest_accepted_handover()
        return handover.created_at if handover is not None else None


class TicketReply(Base):
    __tablename__ = "ticket_reply"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    ticket: Mapped[Ticket] = relationship(back_populates="replies")
    # Eager-loaded so a thread can label each reply with its real author (a
    # trainer, a teaching assistant or an administrator), not just the ticket
    # owner.
    author: Mapped["User"] = relationship(lazy="joined")
    # Eager-loaded so every thread response already carries its media.
    attachments: Mapped[list["TicketAttachment"]] = relationship(
        back_populates="reply",
        order_by="TicketAttachment.created_at",
        lazy="selectin",
    )

    @property
    def author_name(self) -> str | None:
        return self.author.full_name if self.author is not None else None


class TicketAttachment(Base):
    """Image or emoji attached to a ticket reply (AI-89 follow-up media).

    Images live on disk under ``TICKET_STORAGE_DIR``; emojis are stored as the
    characters themselves so a message can carry visual reactions without a
    file upload. ``reply_id`` stays NULL until the reply that owns it is sent.
    """

    __tablename__ = "ticket_attachment"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('IMAGE', 'EMOJI')",
            name="ck_ticket_attachment_kind",
        ),
        CheckConstraint(
            "(kind = 'IMAGE' AND storage_path IS NOT NULL AND mime_type IS NOT NULL) "
            "OR (kind = 'EMOJI' AND emoji IS NOT NULL)",
            name="ck_ticket_attachment_payload",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reply_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ticket_reply.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    emoji: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    ticket: Mapped[Ticket] = relationship(back_populates="attachments")
    reply: Mapped[TicketReply | None] = relationship(back_populates="attachments")
