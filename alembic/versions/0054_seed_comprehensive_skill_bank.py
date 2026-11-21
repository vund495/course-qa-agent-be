"""Seed comprehensive skill bank with 7 domains, 50+ differentiated technical skills, and Dreyfus rubrics.

Revision ID: 0054_seed_skill_bank
Revises: 0053_global_skill_taxonomy
Create Date: 2026-11-20
"""

import logging
import runpy
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from alembic import op
from app.models.skill import Skill, SkillGroup, SkillLevelRubric

logger = logging.getLogger("alembic.migration.0054")

# revision identifiers, used by Alembic.
revision = "0054_seed_skill_bank"
down_revision = "0053_global_skill_taxonomy"
branch_labels = None
depends_on = None

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "skill_bank_data.py"
_MOD = runpy.run_path(str(_DATA_FILE))
SKILL_GROUPS = _MOD["SKILL_GROUPS"]
SKILLS_BANK = _MOD["SKILLS_BANK"]


def seed_skill_bank(db: Session) -> None:
    """Ensure top-level skill groups, comprehensive skill catalog, and rubrics exist."""
    try:
        # Fast exit if skill groups and skills are already seeded
        existing_groups_count = db.query(SkillGroup).count()
        existing_skills_count = db.query(Skill).count()
        if existing_groups_count >= len(SKILL_GROUPS) and existing_skills_count >= len(SKILLS_BANK):
            return

        # 1. Upsert Groups (batch queried)
        existing_groups = {g.code: g for g in db.query(SkillGroup).all()}
        group_map = {}
        for g_data in SKILL_GROUPS:
            group = existing_groups.get(g_data["code"])
            if not group:
                group = SkillGroup(
                    id=g_data["id"],
                    code=g_data["code"],
                    name=g_data["name"],
                    description=g_data["description"],
                )
                db.add(group)
            else:
                group.name = g_data["name"]
                group.description = g_data["description"]
            group_map[g_data["code"]] = group.id
        db.flush()
        for g_data in SKILL_GROUPS:
            if g_data["code"] in existing_groups:
                group_map[g_data["code"]] = existing_groups[g_data["code"]].id

        # 2. Upsert Skills (batch queried)
        existing_skills = {s.code: s for s in db.query(Skill).all()}
        existing_rubrics = {(r.skill_id, r.level): r for r in db.query(SkillLevelRubric).all()}

        for s_data in SKILLS_BANK:
            code = s_data["code"]
            skill = existing_skills.get(code)
            group_code = next((g["code"] for g in SKILL_GROUPS if g["id"] == s_data["group_id"]), None)
            actual_group_id = group_map.get(group_code, s_data["group_id"])

            if not skill:
                skill = Skill(
                    id=s_data["id"],
                    code=code,
                    name=s_data["name"],
                    group_id=actual_group_id,
                    domain=s_data.get("domain"),
                    sub_domain=s_data.get("sub_domain"),
                    skill_family=s_data.get("skill_family"),
                    classification=s_data.get("classification"),
                    description=s_data.get("description"),
                )
                db.add(skill)
                existing_skills[code] = skill
            else:
                skill.name = s_data["name"]
                skill.group_id = actual_group_id
                skill.domain = s_data.get("domain")
                skill.sub_domain = s_data.get("sub_domain")
                skill.skill_family = s_data.get("skill_family")
                skill.classification = s_data.get("classification")
                skill.description = s_data.get("description")

        db.flush()

        # 3. Upsert 5 Dreyfus Rubrics
        for s_data in SKILLS_BANK:
            code = s_data["code"]
            skill = existing_skills[code]
            rubrics = s_data.get("rubrics", {})
            for lvl, desc in rubrics.items():
                th = 80 if lvl == "NOVICE" else (75 if lvl == "BEGINNER" else (70 if lvl == "COMPETENT" else (65 if lvl == "PROFICIENT" else 60)))
                rubric = existing_rubrics.get((skill.id, lvl))
                if rubric:
                    rubric.description = desc
                    rubric.threshold_pct = th
                else:
                    db.add(SkillLevelRubric(
                        id=uuid.uuid4(),
                        skill_id=skill.id,
                        level=lvl,
                        description=desc,
                        threshold_pct=th,
                    ))

        # Re-index all skills sequentially
        all_skills = db.query(Skill).order_by(Skill.group_id, Skill.created_at, Skill.id).all()
        for idx, s in enumerate(all_skills):
            s.display_id = str(idx + 1)

        db.commit()
        logger.info(
            "Successfully seeded skill bank via Alembic (%d skills across %d domains).",
            len(all_skills),
            len(group_map),
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to seed skill bank in Alembic migration")
        raise


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        seed_skill_bank(session)
    finally:
        session.close()


def downgrade() -> None:
    pass
