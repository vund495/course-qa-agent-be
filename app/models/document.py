"""SQLAlchemy model for uploaded learning materials (Epic E2, AI-35/37/41)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.course import Class
    from app.models.user import User


class Document(Base):
    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("class.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Lifecycle mirrors the service statuses: pending -> processing -> indexed,
    # with rejected / failed / replaced as terminal states (Upload AC-02,
    # AI-55 pipeline; replaced = superseded by a newer version, AI-39).
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # AI-39 (AC-03): uploading a file name that already exists in the class
    # creates the next version; version 1 is the original upload.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # True for a syllabus upload even when parsing failed and no preview units
    # exist yet. The approval gate and material targeting still need to see it.
    is_syllabus: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # A material linked to a draft syllabus is private to teachers until the
    # syllabus is published. The flag survives unlinking on draft deletion.
    hidden_from_students: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # A material may be attached to one unit of a syllabus upload. The link is
    # stored as (syllabus document, unit number) so it survives the transition
    # from draft preview to the active SyllabusUnit rows after approval.
    syllabus_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document.id", ondelete="SET NULL"), nullable=True, index=True
    )
    syllabus_unit_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    clazz: Mapped["Class"] = relationship("Class", back_populates="documents")
    uploader: Mapped["User"] = relationship("User", back_populates="documents")
    syllabus_units: Mapped[list["SyllabusUnit"]] = relationship(
        "SyllabusUnit", back_populates="document", cascade="all, delete-orphan"
    )


class SyllabusDraftUnit(Base):
    """Teacher-only preview of a syllabus upload before approval (AI-166).

    Draft units are intentionally stored separately from :class:`SyllabusUnit`
    because the active roadmap has a ``(class_id, unit_number)`` uniqueness
    contract. Parsing a draft must never replace the published roadmap.
    """

    __tablename__ = "syllabus_draft_unit"
    __table_args__ = (
        UniqueConstraint(
            "syllabus_document_id",
            "unit_number",
            name="uq_syllabus_draft_document_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("class.id", ondelete="CASCADE"), nullable=False, index=True
    )
    syllabus_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_number: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    topic_outline: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyllabusUnit(Base):
    """Structured course unit extracted from an indexed syllabus document (AI-133)."""

    __tablename__ = "syllabus_unit"
    __table_args__ = (
        UniqueConstraint("class_id", "unit_number", name="uq_syllabus_unit_class_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("class.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_number: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    topic_outline: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship("Document", back_populates="syllabus_units")

