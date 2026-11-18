"""Merge the syllabus draft units and absence handover heads.

Revision ID: 0047_merge_syllabus_handover
Revises: 0046_syllabus_draft_units, 0046_absence_handover

Both features branched from 0040_quiz_validation. This empty revision joins
them so ``alembic heads`` stays at one without replaying either schema change.
"""

revision = "0047_merge_syllabus_handover"
down_revision = ("0046_syllabus_draft_units", "0046_absence_handover")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
