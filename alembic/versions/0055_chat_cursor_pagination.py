"""Add composite indexes backing chat-history keyset pagination.

Revision ID: 0055_chat_cursor_pagination
Revises: 0054_seed_skill_bank
Create Date: 2026-11-21

The sidebar pages two independent blocks (AI-185):

* ``recent``  — ``WHERE user_id = ? AND is_pinned = false ORDER BY updated_at DESC, id DESC``
* ``pinned``  — ``WHERE user_id = ? AND is_pinned = true  ORDER BY pinned_at ASC,  id ASC``

Each index puts the two equality columns first, then the sort column, then the
``id`` tiebreaker, so the planner walks the index instead of sorting.
"""

from collections.abc import Sequence

from alembic import op

revision = "0055_chat_cursor_pagination"
down_revision = "0054_seed_skill_bank"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_chat_session_user_pinned_updated",
        "chat_session",
        ["user_id", "is_pinned", "updated_at", "id"],
    )
    op.create_index(
        "ix_chat_session_user_pinned_pinned_at",
        "chat_session",
        ["user_id", "is_pinned", "pinned_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_session_user_pinned_pinned_at", table_name="chat_session")
    op.drop_index("ix_chat_session_user_pinned_updated", table_name="chat_session")
