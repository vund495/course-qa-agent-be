"""Extend AI-158 leave with class scope and admin review details.

Legacy coverage, decisions, reason text and ticket history are preserved.
"""

import sqlalchemy as sa

from alembic import op

revision = "0047_admin_leave"
down_revision = "0046_absence_handover"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("leave_request") as batch:
        batch.alter_column("target_trainer_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(sa.Column("class_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_leave_class", "class", ["class_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_index("ix_leave_request_class_id", ["class_id"])
        batch.add_column(
            sa.Column("reason_type", sa.String(40), nullable=False, server_default="other")
        )
        batch.add_column(sa.Column("reason_details", sa.Text(), nullable=True))
        batch.add_column(sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.execute(sa.text("UPDATE leave_request SET reason_details = reason"))


def downgrade():
    # New requests without coverage cannot fit the old NOT NULL contract.
    count = (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM leave_request WHERE target_trainer_id IS NULL"))
        .scalar()
    )
    if count:
        raise RuntimeError(
            "Resolve leave requests without a cover before downgrading; no data was deleted."
        )
    with op.batch_alter_table("leave_request") as batch:
        batch.drop_index("ix_leave_request_class_id")
        batch.drop_constraint("fk_leave_class", type_="foreignkey")
        for column in ("class_id", "reason_type", "reason_details", "rejection_reason"):
            batch.drop_column(column)
        batch.alter_column("target_trainer_id", existing_type=sa.Uuid(), nullable=False)
