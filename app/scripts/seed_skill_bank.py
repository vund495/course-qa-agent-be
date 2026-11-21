"""Standalone CLI script to seed the comprehensive Skill Bank catalog.

Usage:
    python -m app.scripts.seed_skill_bank
"""

import logging
import runpy
import sys
from pathlib import Path

from app.config import settings
from app.core.database import get_session_local, init_engine
from app.models.skill import Skill, SkillGroup

_MIGRATION_FILE = Path(__file__).resolve().parent.parent.parent / "alembic" / "versions" / "0054_seed_comprehensive_skill_bank.py"
_MOD = runpy.run_path(str(_MIGRATION_FILE))
seed_skill_bank = _MOD["seed_skill_bank"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_skill_bank")


def main() -> None:
    logger.info("Connecting to database: %s", settings.database_url)
    init_engine(settings.database_url)
    session_factory = get_session_local(settings.database_url)
    db = session_factory()

    try:
        logger.info("Starting Skill Bank seeding & taxonomy synchronization...")
        seed_skill_bank(db)
        
        group_count = db.query(SkillGroup).count()
        skill_count = db.query(Skill).count()
        
        logger.info("============================================================")
        logger.info("SUCCESS: Skill Bank seeded successfully!")
        logger.info("Total Domains: %d", group_count)
        logger.info("Total Skills:  %d", skill_count)
        logger.info("============================================================")
    except Exception:
        logger.exception("Failed to seed skill bank")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
