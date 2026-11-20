"""Pydantic schemas for Global Skill Taxonomy, Skill Groups, Rubrics, and Class Assignments."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SkillLevel = Literal["NOVICE", "BEGINNER", "COMPETENT", "PROFICIENT", "MASTER"]


# --- Rubric Schemas ---

class SkillLevelRubricBase(BaseModel):
    level: SkillLevel
    description: str = Field(min_length=1, description="Evaluation scope / tested understanding at this level")
    threshold_pct: int = Field(default=70, ge=1, le=100, description="Passing threshold percentage for this level")


class SkillLevelRubricCreate(SkillLevelRubricBase):
    pass


class SkillLevelRubricUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1)
    threshold_pct: int | None = Field(default=None, ge=1, le=100)


class SkillLevelRubricRead(SkillLevelRubricBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    skill_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --- Skill Group Schemas (Top-level domains: Java, Python, SQL) ---

class SkillGroupBase(BaseModel):
    code: str = Field(min_length=1, max_length=50, description="Group code, e.g. JAVA, PYTHON, SQL")
    name: str = Field(min_length=1, max_length=255, description="Display name of the group")
    description: str | None = None


class SkillGroupCreate(SkillGroupBase):
    pass


class SkillGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class SkillGroupRead(SkillGroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    skills_count: int = 0


# --- Skill Course Association Schema ---

class SkillCourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    class_id: uuid.UUID
    class_code: str
    class_name: str
    trainer_name: str | None = None
    semester: str
    academic_year: str
    assigned_at: datetime


# --- Skill Schemas (Sub-skills) ---

class SkillBase(BaseModel):
    code: str = Field(min_length=1, max_length=100, description="Unique skill code, e.g. PY_DATA_TYPES")
    display_id: str | None = Field(default=None, max_length=50, description="Numeric or short display ID, e.g. 93869")
    name: str = Field(min_length=1, max_length=255, description="Display name of the skill")
    group_id: uuid.UUID | None = None
    domain: str | None = Field(default=None, max_length=100)
    sub_domain: str | None = Field(default=None, max_length=100)
    skill_family: str | None = Field(default=None, max_length=100)
    classification: str | None = Field(default=None, max_length=50)
    category: str = Field(default="GENERAL", min_length=1, max_length=100)
    description: str | None = None


class SkillCreate(SkillBase):
    rubrics: list[SkillLevelRubricCreate] = Field(default_factory=list)


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    display_id: str | None = None
    group_id: uuid.UUID | None = None
    domain: str | None = None
    sub_domain: str | None = None
    skill_family: str | None = None
    classification: str | None = None
    category: str | None = None
    description: str | None = None


class SkillRead(SkillBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID | None = None
    group_name: str | None = None
    created_at: datetime
    updated_at: datetime
    rubrics: list[SkillLevelRubricRead] = Field(default_factory=list)
    courses: list[SkillCourseRead] = Field(default_factory=list)


# --- Hierarchical Tree Schema ---

class SkillTreeGroup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    skills: list[SkillRead] = Field(default_factory=list)


# --- Class Skill Association Schemas ---

class ClassSkillAssignPayload(BaseModel):
    skill_ids: list[uuid.UUID] = Field(min_length=1, description="List of skill IDs to assign to the class")


class ClassSkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    skill_id: uuid.UUID
    created_at: datetime
    skill: SkillRead
