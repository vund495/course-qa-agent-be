"""Merge the chat web-consent head with the ticket attachment-names head.

Revision ID: 0051_merge_consent_attachments
Revises: 0049_chat_web_consent, 0050_ticket_attachment_names

The strict-chat consent migration and the ticket attachment-name migration were
created on separate branches. Both applied revisions stay intact; this empty
merge only restores a single Alembic head.
"""

revision = "0051_merge_consent_attachments"
down_revision = ("0049_chat_web_consent", "0050_ticket_attachment_names")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
