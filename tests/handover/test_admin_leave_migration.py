"""Migration preserves legacy reasons and permits uncovered requests."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_upgrade_preserves_reason_and_nullable_cover():
    spec = importlib.util.spec_from_file_location(
        "admin_leave_migration", Path(__file__).parents[2] / "alembic/versions/0047_admin_leave.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE "class" (id CHAR(32) PRIMARY KEY)'))
        conn.execute(
            sa.text(
                "CREATE TABLE leave_request (id CHAR(32) PRIMARY KEY, target_trainer_id CHAR(32) NOT NULL, reason TEXT)"
            )
        )
        conn.execute(
            sa.text("INSERT INTO leave_request VALUES ('old', 'cover', 'Medical appointment')")
        )
        module.op = Operations(MigrationContext.configure(conn))
        module.upgrade()
        row = conn.execute(sa.text("SELECT reason_details, reason_type FROM leave_request")).one()
        assert row == ("Medical appointment", "other")
        conn.execute(sa.text("INSERT INTO leave_request (id, reason) VALUES ('new', NULL)"))
        assert conn.execute(sa.text("SELECT COUNT(*) FROM leave_request")).scalar() == 2
