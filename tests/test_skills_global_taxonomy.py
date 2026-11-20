"""Unit tests for Global Skill Taxonomy, Admin Management, Catalog, and Class Assignments."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.course import Class
from app.models.skill import SkillGroup
from app.models.user import Role, User
from app.routers.skills import (
    admin_create_group,
    admin_create_skill,
    admin_list_groups,
    admin_upsert_rubric,
    assign_skills_to_class,
    get_skills_catalog,
    list_class_skills,
    unassign_skill_from_class,
)
from app.schemas.skill import (
    ClassSkillAssignPayload,
    SkillCreate,
    SkillGroupCreate,
    SkillLevelRubricUpdate,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def admin_user(db: Session) -> User:
    role = Role(name="ADMIN")
    db.add(role)
    db.flush()
    user = User(email="admin@test.com", full_name="Admin", role_id=role.id)
    user.role = role
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def trainer_user(db: Session) -> User:
    role = Role(name="TRAINER")
    db.add(role)
    db.flush()
    user = User(email="trainer@test.com", full_name="Trainer", role_id=role.id)
    user.role = role
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def sample_class(db: Session, trainer_user: User) -> Class:
    clazz = Class(
        code="CS101",
        name="Intro to Programming",
        trainer_id=trainer_user.id,
        credits=3,
        semester="FA26",
        academic_year="2026-2027",
    )
    db.add(clazz)
    db.commit()
    db.refresh(clazz)
    return clazz


def test_admin_group_and_skill_lifecycle(db: Session):
    # 1. Create top-level skill group (Java)
    group = admin_create_group(
        SkillGroupCreate(code="JAVA", name="Java Programming", description="Java topics"),
        db=db,
    )
    assert group.code == "JAVA"
    assert group.name == "Java Programming"

    # 2. List groups
    groups = admin_list_groups(db=db)
    assert len(groups) == 1
    assert groups[0].skills_count == 0

    # 3. Create sub-skill under Java
    skill = admin_create_skill(
        SkillCreate(
            code="JAVA_OOP",
            name="OOP in Java",
            group_id=group.id,
            category="JAVA",
            description="Classes, objects, inheritance",
        ),
        db=db,
    )
    assert skill.code == "JAVA_OOP"
    assert skill.group_id == group.id
    # 5 Dreyfus rubrics auto-bootstrapped
    assert len(skill.rubrics) == 5
    levels = {r.level for r in skill.rubrics}
    assert levels == {"NOVICE", "BEGINNER", "COMPETENT", "PROFICIENT", "MASTER"}

    # 4. Update rubric for Competent
    rubric = admin_upsert_rubric(
        skill_id=skill.id,
        level="COMPETENT",
        payload=SkillLevelRubricUpdate(description="Design inheritance hierarchies", threshold_pct=72),
        db=db,
    )
    assert rubric.threshold_pct == 72
    assert rubric.description == "Design inheritance hierarchies"

    # 5. Check catalog tree
    catalog = get_skills_catalog(db=db, user=None)
    assert len(catalog) == 1
    assert catalog[0].code == "JAVA"
    assert len(catalog[0].skills) == 1
    assert catalog[0].skills[0].code == "JAVA_OOP"


def test_class_teacher_assign_and_unassign(db: Session, trainer_user: User, sample_class: Class):
    # Setup group and skills in DB
    group = SkillGroup(code="PYTHON", name="Python Programming")
    db.add(group)
    db.flush()

    s1 = admin_create_skill(SkillCreate(code="PY_DATA_TYPES", name="Data Types", group_id=group.id), db=db)
    s2 = admin_create_skill(SkillCreate(code="PY_OOP", name="Python OOP", group_id=group.id), db=db)

    # Initially empty
    current = list_class_skills(class_id=sample_class.id, db=db, user=trainer_user)
    assert len(current) == 0

    # Teacher selects and assigns s1 and s2 to class
    assigned = assign_skills_to_class(
        class_id=sample_class.id,
        payload=ClassSkillAssignPayload(skill_ids=[s1.id, s2.id]),
        db=db,
        user=trainer_user,
    )
    assert len(assigned) == 2
    codes = {s.code for s in assigned}
    assert codes == {"PY_DATA_TYPES", "PY_OOP"}

    # Teacher unassigns s1
    unassign_skill_from_class(class_id=sample_class.id, skill_id=s1.id, db=db, user=trainer_user)

    remaining = list_class_skills(class_id=sample_class.id, db=db, user=trainer_user)
    assert len(remaining) == 1
    assert remaining[0].code == "PY_OOP"
