"""Add user-bound web-search consent offers for the strict chat flow.

Revision ID: 0049_chat_web_consent
Revises: 0048_merge_syllabus_admin_leave
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "0049_chat_web_consent"
down_revision = "0048_merge_syllabus_admin_leave"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_web_consent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("class_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=True),
        sa.Column("web_message_id", sa.Uuid(), nullable=True),
        sa.Column("scope_kind", sa.String(length=20), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("scope_segments", sa.JSON(), nullable=False),
        sa.Column("conflict_note", sa.Text(), nullable=True),
        sa.Column("conflict_citations", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'consumed', 'declined', 'expired')",
            name="ck_chat_web_consent_status",
        ),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["chat_message.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["class_id"], ["class.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["web_message_id"], ["chat_message.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_web_consent_class_id", "chat_web_consent", ["class_id"])
    op.create_index("ix_chat_web_consent_session_id", "chat_web_consent", ["session_id"])
    op.create_index("ix_chat_web_consent_status", "chat_web_consent", ["status"])
    op.create_index("ix_chat_web_consent_user_id", "chat_web_consent", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_web_consent_user_id", table_name="chat_web_consent")
    op.drop_index("ix_chat_web_consent_status", table_name="chat_web_consent")
    op.drop_index("ix_chat_web_consent_session_id", table_name="chat_web_consent")
    op.drop_index("ix_chat_web_consent_class_id", table_name="chat_web_consent")
    op.drop_table("chat_web_consent")
