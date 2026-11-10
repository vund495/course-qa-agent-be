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
        Uuid, ForeignKey("chat_message.id", ondelete="SET NULL"), nullable=True,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OPEN", server_default="OPEN"
    )
    # Starts a fresh expiration window when a resolved ticket is reopened.
    reopened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
