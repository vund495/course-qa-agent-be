"""Merge the syllabus/absence head with the AI-140 admin leave head.

Revision ID: 0048_merge_syllabus_admin_leave
Revises: 0047_merge_syllabus_handover, 0047_admin_leave

The database already has 0047_merge_syllabus_handover applied; the upstream
AI-140 migration branches from 0046_absence_handover. This empty merge keeps
both applied revisions intact and restores one head.
"""

revision = "0048_merge_syllabus_admin_leave"
down_revision = ("0047_merge_syllabus_handover", "0047_admin_leave")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
