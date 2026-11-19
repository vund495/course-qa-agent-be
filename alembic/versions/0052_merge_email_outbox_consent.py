"""Merge the email outbox timeline and consent-attachments heads.

Revision ID: 0052_merge_email_outbox_consent
Revises: 0051_merge_consent_attachments, 0051_email_outbox_timeline

Both 0051 revisions were already applied on separate branches. This empty merge
only restores a single Alembic head without changing either applied revision.
"""

revision = "0052_merge_email_outbox_consent"
down_revision = (
    "0051_merge_consent_attachments",
    "0051_email_outbox_timeline",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
