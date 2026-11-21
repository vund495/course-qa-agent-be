"""Global Skill Taxonomy, Skill Groups, Dreyfus Rubrics, and Class Bindings."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.course import Class
    from app.models.quiz import QuizQuestion

from sqlalchemy import (
    CheckConstraint,
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


class SkillGroup(Base):
    """Top-level skill domain or topic (e.g., JAVA, PYTHON, SQL, AI_ML).

    Managed strictly by Administrators.
    """

    __tablename__ = "skill_group"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    skills: Mapped[list["Skill"]] = relationship(
        "Skill",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="Skill.code",
    )


class Skill(Base):
    """Atomic skill entity belonging to a skill group.

    Global master definition managed strictly by Administrators.
    """

    __tablename__ = "skill"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    display_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("skill_group.id", ondelete="CASCADE"), nullable=True, index=True
    )
    class_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("class.id", ondelete="SET NULL"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sub_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skill_family: Mapped[str | None] = mapped_column(String(100), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(50), nullable=True)

    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="GENERAL", server_default="GENERAL", index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    group: Mapped[SkillGroup | None] = relationship("SkillGroup", back_populates="skills")
    rubrics: Mapped[list["SkillLevelRubric"]] = relationship(
        "SkillLevelRubric",
        back_populates="skill",
        cascade="all, delete-orphan",
        order_by="SkillLevelRubric.level",
    )
    class_assignments: Mapped[list["ClassSkill"]] = relationship(
        "ClassSkill",
        back_populates="skill",
        cascade="all, delete-orphan",
    )
    questions: Mapped[list["QuizQuestion"]] = relationship(
        "QuizQuestion",
        back_populates="skill",
    )


class SkillLevelRubric(Base):
    """Evaluation scope defining student understanding required at each Dreyfus level."""

    __tablename__ = "skill_level_rubric"
    __table_args__ = (
        CheckConstraint(
            "level IN ('NOVICE', 'BEGINNER', 'COMPETENT', 'PROFICIENT', 'MASTER')",
            name="ck_skill_level_rubric_level",
        ),
        UniqueConstraint("skill_id", "level", name="uq_skill_level_rubric"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skill.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    threshold_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=70)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    skill: Mapped[Skill] = relationship("Skill", back_populates="rubrics")


class ClassSkill(Base):
    """Association linking an existing global skill to a specific class.

    Trainers select skills from the global catalog to activate in their course.
    """

    __tablename__ = "class_skill"
    __table_args__ = (
        UniqueConstraint("class_id", "skill_id", name="uq_class_skill"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("class.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skill.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    clazz: Mapped["Class"] = relationship("Class", back_populates="skills")
    skill: Mapped[Skill] = relationship("Skill", back_populates="class_assignments")
