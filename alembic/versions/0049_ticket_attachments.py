"""Add image and emoji attachments to ticket replies (AI-89 follow-up media).

Revision ID: 0049_ticket_attachments
Revises: 0048_merge_syllabus_admin_leave
"""

import sqlalchemy as sa

from alembic import op

revision = "0049_ticket_attachments"
down_revision = "0048_merge_syllabus_admin_leave"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_attachment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Uuid(),
            sa.ForeignKey("ticket.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reply_id",
            sa.Uuid(),
            sa.ForeignKey("ticket_reply.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_by",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(length=500), nullable=True),
        sa.Column("emoji", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('IMAGE', 'EMOJI')",
            name="ck_ticket_attachment_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'IMAGE' AND storage_path IS NOT NULL AND mime_type IS NOT NULL) "
            "OR (kind = 'EMOJI' AND emoji IS NOT NULL)",
            name="ck_ticket_attachment_payload",
        ),
    )
    op.create_index("ix_ticket_attachment_ticket_id", "ticket_attachment", ["ticket_id"])
    op.create_index("ix_ticket_attachment_reply_id", "ticket_attachment", ["reply_id"])
    op.create_index("ix_ticket_attachment_uploaded_by", "ticket_attachment", ["uploaded_by"])
    op.create_index("ix_ticket_attachment_created_at", "ticket_attachment", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ticket_attachment_created_at", table_name="ticket_attachment")
    op.drop_index("ix_ticket_attachment_uploaded_by", table_name="ticket_attachment")
    op.drop_index("ix_ticket_attachment_reply_id", table_name="ticket_attachment")
    op.drop_index("ix_ticket_attachment_ticket_id", table_name="ticket_attachment")
    op.drop_table("ticket_attachment")
