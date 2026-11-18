"""Keep only the attachment file name so a row survives a host/Docker switch.

Rows used to store the absolute path written by whichever machine handled the
upload (``/app/storage/tickets/...`` from the Docker backend, a Windows drive
path from a host run). The same shared DB then could not serve those files from
another environment, so the path is reduced to the file name; the storage root is
always ``settings.ticket_storage_dir``.

Revision ID: 0050_ticket_attachment_names
Revises: 0049_ticket_attachments
"""

from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision = "0050_ticket_attachment_names"
down_revision = "0049_ticket_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, storage_path FROM ticket_attachment WHERE storage_path IS NOT NULL")
    ).fetchall()
    for attachment_id, storage_path in rows:
        # Windows and POSIX separators both appear in existing rows.
        name = Path(str(storage_path).replace("\\", "/")).name
        if not name or name == storage_path:
            continue
        connection.execute(
            sa.text("UPDATE ticket_attachment SET storage_path = :name WHERE id = :id"),
            {"name": name, "id": attachment_id},
        )


def downgrade() -> None:
    """Irreversible: the original absolute path is not recoverable."""
