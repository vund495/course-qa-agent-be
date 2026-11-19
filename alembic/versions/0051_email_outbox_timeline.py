"""Add per-transition timestamps to the email outbox.

AI-138 AC-04: the outbox only had ``created_at`` and ``sent_at``, so a failed
attempt left no trace of when it happened and the admin timeline could not be
reconstructed. ``last_attempt_at`` records every drain attempt and ``failed_at``
records the last failure.

Revision ID: 0051_email_outbox_timeline
Revises: 0050_ticket_attachment_names
"""

import sqlalchemy as sa

from alembic import op

revision = "0051_email_outbox_timeline"
down_revision = "0050_ticket_attachment_names"
branch_labels = None
depends_on = None


def _columns(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "email_outbox" not in insp.get_table_names():
        return
    existing = _columns(insp, "email_outbox")
    with op.batch_alter_table("email_outbox") as batch:
        if "last_attempt_at" not in existing:
            batch.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        if "failed_at" not in existing:
            batch.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "email_outbox" not in insp.get_table_names():
        return
    existing = _columns(insp, "email_outbox")
    with op.batch_alter_table("email_outbox") as batch:
        if "failed_at" in existing:
            batch.drop_column("failed_at")
        if "last_attempt_at" in existing:
            batch.drop_column("last_attempt_at")
