"""Add draft syllabus units and per-unit material links (AI-166).

Revision ID: 0046_syllabus_draft_units
Revises: 0040_quiz_validation
"""

import sqlalchemy as sa

from alembic import op

revision = "0046_syllabus_draft_units"
down_revision = "0040_quiz_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "syllabus_draft_unit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("class_id", sa.Uuid(), sa.ForeignKey("class.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "syllabus_document_id",
            sa.Uuid(),
            sa.ForeignKey("document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("unit_number", sa.Integer(), nullable=False),
        sa.Column("unit_title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("topic_outline", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "syllabus_document_id",
            "unit_number",
            name="uq_syllabus_draft_document_number",
        ),
    )
    op.create_index(
        "ix_syllabus_draft_unit_class_id",
        "syllabus_draft_unit",
        ["class_id"],
    )
    op.create_index(
        "ix_syllabus_draft_unit_syllabus_document_id",
        "syllabus_draft_unit",
        ["syllabus_document_id"],
    )

    with op.batch_alter_table("document") as batch:
        batch.add_column(
            sa.Column(
                "is_syllabus",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "hidden_from_students",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(sa.Column("syllabus_document_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("syllabus_unit_number", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_document_syllabus_document_id",
            "document",
            ["syllabus_document_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_document_syllabus_document_id",
            ["syllabus_document_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("document") as batch:
        batch.drop_index("ix_document_syllabus_document_id")
        batch.drop_constraint("fk_document_syllabus_document_id", type_="foreignkey")
        batch.drop_column("syllabus_unit_number")
        batch.drop_column("syllabus_document_id")
        batch.drop_column("hidden_from_students")
        batch.drop_column("is_syllabus")

    op.drop_index("ix_syllabus_draft_unit_syllabus_document_id", table_name="syllabus_draft_unit")
    op.drop_index("ix_syllabus_draft_unit_class_id", table_name="syllabus_draft_unit")
    op.drop_table("syllabus_draft_unit")
