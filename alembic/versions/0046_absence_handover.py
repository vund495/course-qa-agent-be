"""Add ticket ownership, trainer day status and leave requests (AI-158).

Revision ID: 0046_absence_handover
Revises: 0040_quiz_validation
Create Date: 2026-11-10
"""

import sqlalchemy as sa

from alembic import op

revision = "0046_absence_handover"
down_revision = "0040_quiz_validation"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _existing_indexes(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _ticket_has_owner_fk() -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        "owner_trainer_id" in foreign_key.get("constrained_columns", [])
        for foreign_key in inspector.get_foreign_keys("ticket")
    )


def upgrade() -> None:
    existing = _existing_tables()

    if "ticket" in existing:
        ticket_columns = _existing_columns("ticket")
        ticket_indexes = _existing_indexes("ticket")
        has_owner_fk = _ticket_has_owner_fk()

        with op.batch_alter_table("ticket") as batch:
            if "owner_trainer_id" not in ticket_columns:
                batch.add_column(sa.Column("owner_trainer_id", sa.Uuid(), nullable=True))
            if "queued_for_admin_at" not in ticket_columns:
                batch.add_column(
                    sa.Column(
                        "queued_for_admin_at",
                        sa.DateTime(timezone=True),
                        nullable=True,
                    )
                )
            if not has_owner_fk:
                batch.create_foreign_key(
                    "fk_ticket_owner_trainer_id_user",
                    "user",
                    ["owner_trainer_id"],
                    ["id"],
                    ondelete="SET NULL",
                )

        if "ix_ticket_owner_trainer_id" not in ticket_indexes:
            op.create_index("ix_ticket_owner_trainer_id", "ticket", ["owner_trainer_id"])
        if "ix_ticket_queued_for_admin_at" not in ticket_indexes:
            op.create_index(
                "ix_ticket_queued_for_admin_at",
                "ticket",
                ["queued_for_admin_at"],
            )

        op.execute(
            sa.text(
                """
                UPDATE ticket
                SET owner_trainer_id = (
                    SELECT trainer_id
                    FROM class
                    WHERE class.id = ticket.class_id
                )
                WHERE owner_trainer_id IS NULL
                """
            )
        )

    if "trainer_day_status" not in existing:
        op.create_table(
            "trainer_day_status",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("trainer_id", sa.Uuid(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("recorded_by", sa.Uuid(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "status IN ('present', 'off')",
                name="ck_trainer_day_status_status",
            ),
            sa.ForeignKeyConstraint(["trainer_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["recorded_by"], ["user.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "trainer_id",
                "date",
                name="uq_trainer_day_status_trainer_date",
            ),
        )
        op.create_index(
            "ix_trainer_day_status_date_status",
            "trainer_day_status",
            ["date", "status"],
        )

    if "leave_request" not in existing:
        op.create_table(
            "leave_request",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("trainer_id", sa.Uuid(), nullable=False),
            sa.Column("date_from", sa.Date(), nullable=False),
            sa.Column("date_to", sa.Date(), nullable=False),
            sa.Column("target_trainer_id", sa.Uuid(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("responded_by", sa.Uuid(), nullable=True),
            sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint("date_to >= date_from", name="ck_leave_request_dates"),
            sa.CheckConstraint(
                "status IN ('pending', 'accepted', 'rejected')",
                name="ck_leave_request_status",
            ),
            sa.CheckConstraint(
                "trainer_id <> target_trainer_id",
                name="ck_leave_request_same_trainer",
            ),
            sa.ForeignKeyConstraint(["trainer_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["target_trainer_id"],
                ["user.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(["responded_by"], ["user.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_leave_request_trainer_status",
            "leave_request",
            ["trainer_id", "status"],
        )


def downgrade() -> None:
    existing = _existing_tables()

    if "leave_request" in existing:
        op.drop_table("leave_request")
    if "trainer_day_status" in existing:
        op.drop_table("trainer_day_status")

    if "ticket" in existing:
        ticket_columns = _existing_columns("ticket")
        ticket_indexes = _existing_indexes("ticket")

        if "ix_ticket_queued_for_admin_at" in ticket_indexes:
            op.drop_index("ix_ticket_queued_for_admin_at", table_name="ticket")
        if "ix_ticket_owner_trainer_id" in ticket_indexes:
            op.drop_index("ix_ticket_owner_trainer_id", table_name="ticket")

        with op.batch_alter_table("ticket") as batch:
            if "queued_for_admin_at" in ticket_columns:
                batch.drop_column("queued_for_admin_at")
            if "owner_trainer_id" in ticket_columns:
                batch.drop_column("owner_trainer_id")
