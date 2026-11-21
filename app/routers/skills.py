"""Routers for Global Skill Taxonomy, Admin Management, Catalog, and Class Bindings.

- Admin Router: CRUD for Skill Groups, Sub-skills, and Dreyfus Rubrics.
- Catalog Router: Public tree hierarchy of all skills for trainers to browse.
- Class Router: Assign/unassign existing skills to a specific class.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user, get_db, require_admin
from app.models.course import Class
from app.models.skill import ClassSkill, Skill, SkillGroup, SkillLevelRubric
from app.models.user import User
from app.schemas.skill import (
    ClassSkillAssignPayload,
    SkillCourseRead,
    SkillCreate,
    SkillGroupCreate,
    SkillGroupRead,
    SkillGroupUpdate,
    SkillLevelRubricRead,
    SkillLevelRubricUpdate,
    SkillRead,
    SkillTreeGroup,
    SkillUpdate,
)
from app.services import course_service, user_service
from app.services.skill_taxonomy_service import normalize_skill_code

DEFAULT_THRESHOLDS = {
    "NOVICE": 80,
    "BEGINNER": 75,
    "COMPETENT": 70,
    "PROFICIENT": 65,
    "MASTER": 60,
}

DEFAULT_RUBRIC_DESCRIPTIONS = {
    "NOVICE": "The individual with no experience or no understanding to perform the task.",
    "BEGINNER": "Understands the foundational purpose and basic use cases of the skill. Possesses basic theoretical knowledge of core principles and can perform very simple, guided tasks using standard templates, but requires significant guidance for customization.",
    "COMPETENT": "Demonstrates a working understanding of core concepts and functionalities. Able to independently apply core mechanisms to build standard workflows and resolve common implementation issues with occasional assistance on complex configurations.",
    "PROFICIENT": "Exhibits strong proficiency in designing and building complex workflows and pipelines tailored to specific requirements. Capable of developing custom components, optimizing execution performance, and providing guidance and mentorship on best practices.",
    "MASTER": "Mastery of the skill with near-flawless execution. Considered an authoritative expert, establishing architectural standards, creating innovative production-grade solutions, and actively contributing to community or organizational thought leadership.",
}

# ============================================================================
# Helpers
# ============================================================================

def _require_class_teacher(db: Session, user: User, class_id: uuid.UUID) -> Class:
    """Allow admins, the primary trainer, or co-trainers of this class."""
    section = course_service.get_class(db, class_id)
    if section is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")
    role = (user_service.role_name_of(user) or "").upper()
    if role == "ADMIN":
        return section
    if role == "TRAINER" and section.id in course_service.class_ids_for_trainer(db, user.id):
        return section
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only an administrator or a trainer of this class can manage skills.",
    )


def _serialize_skill(db: Session, skill: Skill) -> SkillRead:
    # Query integrated courses / classes
    stmt_courses = (
        select(Class, User.full_name, ClassSkill.created_at)
        .join(ClassSkill, ClassSkill.class_id == Class.id)
        .outerjoin(User, User.id == Class.trainer_id)
        .where(ClassSkill.skill_id == skill.id)
        .order_by(Class.code)
    )
    course_rows = db.execute(stmt_courses).all()
    courses = [
        SkillCourseRead(
            class_id=cls.id,
            class_code=cls.code,
            class_name=cls.name,
            trainer_name=full_name,
            semester=cls.semester,
            academic_year=cls.academic_year,
            assigned_at=created_at,
        )
        for cls, full_name, created_at in course_rows
    ]

    # Include legacy bound class if not already present
    if skill.class_id and not any(c.class_id == skill.class_id for c in courses):
        legacy_row = db.execute(
            select(Class, User.full_name)
            .outerjoin(User, User.id == Class.trainer_id)
            .where(Class.id == skill.class_id)
        ).first()
        if legacy_row:
            cls, full_name = legacy_row
            courses.append(
                SkillCourseRead(
                    class_id=cls.id,
                    class_code=cls.code,
                    class_name=cls.name,
                    trainer_name=full_name,
                    semester=cls.semester,
                    academic_year=cls.academic_year,
                    assigned_at=skill.created_at,
                )
            )

    if skill.display_id and skill.display_id.strip():
        display_id = skill.display_id.strip()
    else:
        display_id = "1"

    return SkillRead(
        id=skill.id,
        display_id=display_id,
        group_id=skill.group_id,
        group_name=skill.group.name if skill.group else None,
        code=skill.code,
        name=skill.name,
        domain=skill.domain,
        sub_domain=skill.sub_domain,
        skill_family=skill.skill_family,
        classification=skill.classification,
        category=skill.category,
        description=skill.description,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
        rubrics=[SkillLevelRubricRead.model_validate(r) for r in skill.rubrics],
        courses=courses,
    )


# ============================================================================
# 1. ADMIN SKILL TAXONOMY ROUTER (/api/admin/skills)
# ============================================================================

admin_skills_router = APIRouter(
    prefix="/api/admin/skills",
    tags=["admin-skills"],
    dependencies=[Depends(require_admin)],
)


# --- Skill Groups (Top-level domains) ---

@admin_skills_router.get("/groups", response_model=list[SkillGroupRead])
def admin_list_groups(db: Session = Depends(get_db)) -> list[SkillGroupRead]:
    """List all top-level skill groups with their count of sub-skills."""
    stmt = (
        select(SkillGroup, func.count(Skill.id).label("skills_count"))
        .outerjoin(Skill, Skill.group_id == SkillGroup.id)
        .group_by(SkillGroup.id)
        .order_by(SkillGroup.code)
    )
    results = db.execute(stmt).all()
    output: list[SkillGroupRead] = []
    for group, count in results:
        read_obj = SkillGroupRead.model_validate(group)
        read_obj.skills_count = count
        output.append(read_obj)
    return output


@admin_skills_router.post("/groups", response_model=SkillGroupRead, status_code=status.HTTP_201_CREATED)
def admin_create_group(payload: SkillGroupCreate, db: Session = Depends(get_db)) -> SkillGroupRead:
    """Create a new top-level skill group (e.g., JAVA, PYTHON, SQL)."""
    code = payload.code.strip().upper()
    existing = db.scalar(select(SkillGroup).where(SkillGroup.code == code))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Skill group '{code}' already exists.")

    group = SkillGroup(
        code=code,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    read_obj = SkillGroupRead.model_validate(group)
    read_obj.skills_count = 0
    return read_obj


@admin_skills_router.patch("/groups/{group_id}", response_model=SkillGroupRead)
def admin_update_group(group_id: uuid.UUID, payload: SkillGroupUpdate, db: Session = Depends(get_db)) -> SkillGroupRead:
    """Update a skill group's display name or description."""
    group = db.scalar(select(SkillGroup).where(SkillGroup.id == group_id))
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill group not found.")

    if payload.name is not None:
        group.name = payload.name.strip()
    if payload.description is not None:
        group.description = payload.description.strip() if payload.description else None

    db.commit()
    db.refresh(group)
    count = db.scalar(select(func.count(Skill.id)).where(Skill.group_id == group_id)) or 0
    read_obj = SkillGroupRead.model_validate(group)
    read_obj.skills_count = count
    return read_obj


@admin_skills_router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_group(group_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    """Delete a skill group and cascade delete all its sub-skills."""
    group = db.scalar(select(SkillGroup).where(SkillGroup.id == group_id))
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill group not found.")
    db.delete(group)
    db.commit()


# --- Sub-skills Management ---

@admin_skills_router.get("", response_model=list[SkillRead])
def admin_list_skills(
    group_id: Annotated[uuid.UUID | None, Query(description="Filter by group ID")] = None,
    search: Annotated[str | None, Query(description="Search in code or name")] = None,
    db: Session = Depends(get_db),
) -> list[SkillRead]:
    """List all global sub-skills with their Dreyfus rubrics and course integration."""
    stmt = (
        select(Skill)
        .options(selectinload(Skill.rubrics), selectinload(Skill.group))
        .order_by(Skill.code)
    )
    if group_id:
        stmt = stmt.where(Skill.group_id == group_id)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            (Skill.name.ilike(pattern))
            | (Skill.code.ilike(pattern))
            | (Skill.skill_family.ilike(pattern))
            | (Skill.domain.ilike(pattern))
            | (Skill.sub_domain.ilike(pattern))
            | (Skill.classification.ilike(pattern))
        )

    skills = list(db.scalars(stmt).all())

    def sort_key(s):
        try:
            return (0, int(s.display_id))
        except (ValueError, TypeError):
            return (1, s.display_id or s.code)

    skills.sort(key=sort_key)
    return [_serialize_skill(db, s) for s in skills]


@admin_skills_router.post("", response_model=SkillRead, status_code=status.HTTP_201_CREATED)
def admin_create_skill(payload: SkillCreate, db: Session = Depends(get_db)) -> SkillRead:
    """Manually create a sub-skill and its 5-level Dreyfus rubrics."""
    code = normalize_skill_code(payload.code)
    existing = db.scalar(select(Skill).where(Skill.code == code))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Skill code '{code}' already exists.")

    if payload.group_id:
        group = db.scalar(select(SkillGroup).where(SkillGroup.id == payload.group_id))
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referenced skill group not found.")

    if payload.display_id and payload.display_id.strip():
        display_id = payload.display_id.strip()
    else:
        # Sequential ID starting from 1
        count = db.scalar(select(func.count(Skill.id))) or 0
        display_id = str(count + 1)

    skill = Skill(
        group_id=payload.group_id,
        display_id=display_id,
        code=code,
        name=payload.name.strip(),
        domain=payload.domain.strip() if payload.domain else None,
        sub_domain=payload.sub_domain.strip() if payload.sub_domain else None,
        skill_family=payload.skill_family.strip() if payload.skill_family else None,
        classification=payload.classification.strip() if payload.classification else None,
        category=payload.category.strip().upper() if payload.category else "GENERAL",
        description=payload.description.strip() if payload.description else None,
    )
    db.add(skill)
    db.flush()

    provided_levels = {r.level.upper(): r for r in payload.rubrics}
    for lvl, default_pct in DEFAULT_THRESHOLDS.items():
        if lvl in provided_levels:
            r_in = provided_levels[lvl]
            rubric = SkillLevelRubric(
                skill_id=skill.id,
                level=lvl,
                description=r_in.description.strip(),
                threshold_pct=r_in.threshold_pct or default_pct,
            )
        else:
            rubric = SkillLevelRubric(
                skill_id=skill.id,
                level=lvl,
                description=DEFAULT_RUBRIC_DESCRIPTIONS[lvl],
                threshold_pct=default_pct,
            )
        db.add(rubric)

    db.commit()
    db.refresh(skill)
    loaded = db.scalar(
        select(Skill)
        .where(Skill.id == skill.id)
        .options(selectinload(Skill.rubrics), selectinload(Skill.group))
    )
    return _serialize_skill(db, loaded or skill)


@admin_skills_router.get("/{skill_id}", response_model=SkillRead)
def admin_get_skill(skill_id: uuid.UUID, db: Session = Depends(get_db)) -> SkillRead:
    """Get single sub-skill details with all 5 rubrics and integrated courses."""
    skill = db.scalar(
        select(Skill)
        .where(Skill.id == skill_id)
        .options(selectinload(Skill.rubrics), selectinload(Skill.group))
    )
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found.")
    return _serialize_skill(db, skill)


@admin_skills_router.patch("/{skill_id}", response_model=SkillRead)
def admin_update_skill(skill_id: uuid.UUID, payload: SkillUpdate, db: Session = Depends(get_db)) -> SkillRead:
    """Update a sub-skill metadata."""
    skill = db.scalar(
        select(Skill)
        .where(Skill.id == skill_id)
        .options(selectinload(Skill.rubrics), selectinload(Skill.group))
    )
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found.")

    if payload.name is not None:
        skill.name = payload.name.strip()
    if payload.display_id is not None:
        skill.display_id = payload.display_id.strip()
    if payload.group_id is not None:
        skill.group_id = payload.group_id
    if payload.domain is not None:
        skill.domain = payload.domain.strip()
    if payload.sub_domain is not None:
        skill.sub_domain = payload.sub_domain.strip()
    if payload.skill_family is not None:
        skill.skill_family = payload.skill_family.strip()
    if payload.classification is not None:
        skill.classification = payload.classification.strip()
    if payload.category is not None:
        skill.category = payload.category.strip().upper()
    if payload.description is not None:
        skill.description = payload.description.strip() if payload.description else None

    db.commit()
    db.refresh(skill)
    return _serialize_skill(db, skill)


@admin_skills_router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_skill(skill_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    """Delete a sub-skill and its rubrics."""
    skill = db.scalar(select(Skill).where(Skill.id == skill_id))
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found.")
    db.delete(skill)
    db.commit()


@admin_skills_router.put("/{skill_id}/rubrics/{level}", response_model=SkillLevelRubricRead)
def admin_upsert_rubric(
    skill_id: uuid.UUID,
    level: str,
    payload: SkillLevelRubricUpdate,
    db: Session = Depends(get_db),
) -> SkillLevelRubric:
    """Manually update or define rubric description & threshold percentage for a level."""
    level_upper = level.upper()
    if level_upper not in DEFAULT_THRESHOLDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid proficiency level.")

    skill = db.scalar(select(Skill).where(Skill.id == skill_id))
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found.")

    rubric = db.scalar(
        select(SkillLevelRubric).where(
            SkillLevelRubric.skill_id == skill_id,
            SkillLevelRubric.level == level_upper,
        )
    )

    if not rubric:
        if not payload.description:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rubric description is required.")
        rubric = SkillLevelRubric(
            skill_id=skill_id,
            level=level_upper,
            description=payload.description.strip(),
            threshold_pct=payload.threshold_pct or DEFAULT_THRESHOLDS[level_upper],
        )
        db.add(rubric)
    else:
        if payload.description is not None:
            rubric.description = payload.description.strip()
        if payload.threshold_pct is not None:
            rubric.threshold_pct = payload.threshold_pct

    db.commit()
    db.refresh(rubric)
    return rubric


# ============================================================================
# 2. CATALOG ROUTER (/api/skills/catalog)
# ============================================================================

catalog_router = APIRouter(prefix="/api/skills", tags=["skills-catalog"])


@catalog_router.get("/catalog", response_model=list[SkillTreeGroup])
def get_skills_catalog(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SkillTreeGroup]:
    """Return the global skill taxonomy tree (Groups -> Sub-skills -> Rubrics)."""
    groups = db.scalars(
        select(SkillGroup)
        .options(
            selectinload(SkillGroup.skills).selectinload(Skill.rubrics),
            selectinload(SkillGroup.skills).selectinload(Skill.group),
        )
        .order_by(SkillGroup.code)
    ).all()

    output: list[SkillTreeGroup] = []
    for g in groups:
        # Sort skills within group by display_id numerically
        group_skills = list(g.skills)
        def sort_key(s):
            try:
                return (0, int(s.display_id))
            except (ValueError, TypeError):
                return (1, s.display_id or s.code)
        group_skills.sort(key=sort_key)

        tree_group = SkillTreeGroup(
            id=g.id,
            code=g.code,
            name=g.name,
            description=g.description,
            skills=[_serialize_skill(db, s) for s in group_skills],
        )
        output.append(tree_group)
    return output


# ============================================================================
# 3. CLASS SKILLS ROUTER (/api/classes/{class_id}/skills)
# ============================================================================

router = APIRouter(prefix="/api/classes/{class_id}/skills", tags=["class-skills"])


@router.get("", response_model=list[SkillRead])
def list_class_skills(
    class_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SkillRead]:
    """List all global skills assigned to this class."""
    _require_class_teacher(db, user, class_id)

    # 1. Fetch skills linked via class_skill association
    stmt_assigned = (
        select(Skill)
        .join(ClassSkill, ClassSkill.skill_id == Skill.id)
        .where(ClassSkill.class_id == class_id)
        .options(selectinload(Skill.rubrics), selectinload(Skill.group))
        .order_by(Skill.category, Skill.code)
    )
    assigned_skills = list(db.scalars(stmt_assigned).all())

    # 2. Also include legacy skills where skill.class_id == class_id
    stmt_legacy = (
        select(Skill)
        .where(Skill.class_id == class_id)
        .options(selectinload(Skill.rubrics), selectinload(Skill.group))
        .order_by(Skill.category, Skill.code)
    )
    legacy_skills = list(db.scalars(stmt_legacy).all())

    seen_ids = set()
    combined: list[Skill] = []
    for s in assigned_skills + legacy_skills:
        if s.id not in seen_ids:
            seen_ids.add(s.id)
            combined.append(s)

    return [_serialize_skill(db, s) for s in combined]


@router.post("/assign", response_model=list[SkillRead], status_code=status.HTTP_200_OK)
def assign_skills_to_class(
    class_id: uuid.UUID,
    payload: ClassSkillAssignPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SkillRead]:
    """Assign existing skills from the global catalog into this class."""
    _require_class_teacher(db, user, class_id)

    if not payload.skill_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No skills selected.")

    skills = db.scalars(select(Skill).where(Skill.id.in_(payload.skill_ids))).all()
    found_ids = {s.id for s in skills}
    missing = set(payload.skill_ids) - found_ids
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skills not found in catalog: {list(missing)}",
        )

    existing_assignments = set(
        db.scalars(
            select(ClassSkill.skill_id).where(ClassSkill.class_id == class_id)
        ).all()
    )

    for sid in payload.skill_ids:
        if sid not in existing_assignments:
            db.add(ClassSkill(class_id=class_id, skill_id=sid))

    db.commit()
    return list_class_skills(class_id, db, user)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_skill_from_class(
    class_id: uuid.UUID,
    skill_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Unassign a skill from this class."""
    _require_class_teacher(db, user, class_id)

    assignment = db.scalar(
        select(ClassSkill).where(ClassSkill.class_id == class_id, ClassSkill.skill_id == skill_id)
    )
    if assignment:
        db.delete(assignment)

    legacy = db.scalar(
        select(Skill).where(Skill.id == skill_id, Skill.class_id == class_id)
    )
    if legacy:
        legacy.class_id = None

    db.commit()
