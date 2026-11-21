"""Regression tests for the syllabus/absence Alembic head merge (AI-166/AI-158)."""

import uuid

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

LEGACY_SYLLABUS_REVISION = "0046_syllabus_draft_units"
UPSTREAM_ABSENCE_REVISION = "0046_absence_handover"
SYLLABUS_MERGE_REVISION = "0047_merge_syllabus_handover"
ADMIN_LEAVE_REVISION = "0047_admin_leave"
MERGE_REVISION = "0048_merge_syllabus_admin_leave"
CHAT_WEB_CONSENT_REVISION = "0049_chat_web_consent"
TICKET_ATTACHMENT_NAMES_REVISION = "0050_ticket_attachment_names"
CONSENT_ATTACHMENTS_MERGE_REVISION = "0051_merge_consent_attachments"
EMAIL_OUTBOX_REVISION = "0051_email_outbox_timeline"
EMAIL_MERGE_REVISION = "0052_merge_email_outbox_consent"
SKILL_TAXONOMY_REVISION = "0053_global_skill_taxonomy"
SKILL_BANK_REVISION = "0054_seed_skill_bank"
HEAD_REVISION = "0055_chat_cursor_pagination"

BASELINE_DDL = (
    'CREATE TABLE "user" (id CHAR(32) PRIMARY KEY)',
    'CREATE TABLE "class" (id CHAR(32) PRIMARY KEY)',
    'CREATE TABLE "document" (id CHAR(32) PRIMARY KEY)',
    'CREATE TABLE "ticket" (id CHAR(32) PRIMARY KEY, class_id CHAR(32), trainer_id CHAR(32))',
    # 0053 alters the class-scoped skill table from 0041, 0054 seeds
    # skill/skill_group/skill_level_rubric, and 0055 indexes chat_session.
    # Those tables predate 0040 in a real database but live on other branches
    # of the migration graph, so recreate their pre-0053 shape for SQLite.
    (
        'CREATE TABLE "skill" ('
        "id CHAR(32) PRIMARY KEY, class_id CHAR(32), code VARCHAR(100) NOT NULL, "
        "name VARCHAR(255) NOT NULL, category VARCHAR(100) NOT NULL DEFAULT 'GENERAL', "
        "description TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
    ),
    (
        'CREATE TABLE "skill_level_rubric" ('
        "id CHAR(32) PRIMARY KEY, skill_id CHAR(32) NOT NULL, level VARCHAR(20) NOT NULL, "
        "description TEXT NOT NULL, threshold_pct INTEGER NOT NULL DEFAULT 70, "
        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
    ),
    (
        'CREATE TABLE "chat_session" ('
        "id CHAR(32) PRIMARY KEY, user_id CHAR(32), "
        "is_pinned BOOLEAN NOT NULL DEFAULT 0, updated_at DATETIME, pinned_at DATETIME)"
    ),
)


def _config(db_path) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _prepare_branch_point(tmp_path, filename: str) -> tuple[Config, str]:
    """Create the minimal schema shared at 0040 and stamp the branch point."""
    db_path = tmp_path / filename
    cfg = _config(db_path)
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        for ddl in BASELINE_DDL:
            conn.execute(sa.text(ddl))
    engine.dispose()
    command.stamp(cfg, "0040_quiz_validation")
    return cfg, f"sqlite:///{db_path}"


def _insert_syllabus_sentinel(engine) -> tuple[str, str]:
    class_id = uuid.uuid4().hex
    document_id = uuid.uuid4().hex
    unit_id = uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(sa.text('INSERT INTO "class" (id) VALUES (:id)'), {"id": class_id})
        conn.execute(
            sa.text("INSERT INTO document (id) VALUES (:id)"),
            {"id": document_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO syllabus_draft_unit"
                " (id, class_id, syllabus_document_id, unit_number, unit_title,"
                " description, content, topic_outline)"
                " VALUES (:id, :class_id, :document_id, 1, 'Legacy Unit', NULL,"
                " 'sentinel content', NULL)"
            ),
            {"id": unit_id, "class_id": class_id, "document_id": document_id},
        )
        conn.execute(
            sa.text(
                "UPDATE document SET is_syllabus = 1, hidden_from_students = 0,"
                " syllabus_document_id = :document_id, syllabus_unit_number = 1"
                " WHERE id = :document_id"
            ),
            {"document_id": document_id},
        )
    return unit_id, document_id


def _create_email_outbox_with_sentinel(engine) -> str:
    message_id = uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE email_outbox ("
                "id CHAR(32) PRIMARY KEY, created_at DATETIME, sent_at DATETIME)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO email_outbox (id, created_at, sent_at)"
                " VALUES (:id, CURRENT_TIMESTAMP, NULL)"
            ),
            {"id": message_id},
        )
    return message_id


def _assert_email_outbox_migrated(url: str, message_id: str) -> None:
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == HEAD_REVISION
        columns = {column["name"] for column in sa.inspect(conn).get_columns("email_outbox")}
        assert {"last_attempt_at", "failed_at"} <= columns
        preserved = conn.execute(
            sa.text("SELECT id FROM email_outbox WHERE id = :id"),
            {"id": message_id},
        ).scalar_one_or_none()
        assert preserved == message_id
    engine.dispose()


def test_upgrade_from_legacy_syllabus_revision_preserves_data(tmp_path):
    """A database already at the old local revision must gain the absence branch."""
    cfg, url = _prepare_branch_point(tmp_path, "legacy_syllabus.db")
    command.upgrade(cfg, LEGACY_SYLLABUS_REVISION)

    engine = sa.create_engine(url)
    unit_id, document_id = _insert_syllabus_sentinel(engine)
    engine.dispose()

    # Reach the revision already applied in the real database, then apply the
    # upstream AI-140 branch and the final merge.
    command.upgrade(cfg, SYLLABUS_MERGE_REVISION)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == HEAD_REVISION

        unit = conn.execute(
            sa.text("SELECT unit_title, content FROM syllabus_draft_unit WHERE id = :id"),
            {"id": unit_id},
        ).one()
        assert unit == ("Legacy Unit", "sentinel content")
        assert (
            conn.execute(sa.text("SELECT count(*) FROM syllabus_draft_unit")).scalar_one() == 1
        )

        document = conn.execute(
            sa.text(
                "SELECT is_syllabus, hidden_from_students, syllabus_document_id,"
                " syllabus_unit_number FROM document WHERE id = :id"
            ),
            {"id": document_id},
        ).one()
        assert bool(document[0]) is True
        assert bool(document[1]) is False
        assert document[2] == document_id
        assert document[3] == 1

        tables = set(sa.inspect(conn).get_table_names())
        assert {"leave_request", "trainer_day_status"} <= tables
        leave_columns = {
            column["name"] for column in sa.inspect(conn).get_columns("leave_request")
        }
        assert {"class_id", "reason_type", "reason_details", "rejection_reason"} <= leave_columns
        ticket_columns = {column["name"] for column in sa.inspect(conn).get_columns("ticket")}
        assert {"owner_trainer_id", "queued_for_admin_at"} <= ticket_columns
    engine.dispose()


def test_fresh_branch_point_upgrade_reaches_single_merge_head(tmp_path):
    """A fresh database from the shared branch point reaches both features."""
    cfg, url = _prepare_branch_point(tmp_path, "fresh_branch.db")
    command.upgrade(cfg, "head")

    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [HEAD_REVISION]

    engine = sa.create_engine(url)
    tables = set(sa.inspect(engine).get_table_names())
    assert {"syllabus_draft_unit", "leave_request", "trainer_day_status"} <= tables
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == HEAD_REVISION
    engine.dispose()


def test_upgrade_from_upstream_absence_head_adds_syllabus_schema(tmp_path):
    """A database already at the upstream head must gain the syllabus branch."""
    cfg, url = _prepare_branch_point(tmp_path, "upstream_absence.db")
    command.upgrade(cfg, UPSTREAM_ABSENCE_REVISION)

    engine = sa.create_engine(url)
    pre_upgrade_tables = set(sa.inspect(engine).get_table_names())
    assert {"leave_request", "trainer_day_status"} <= pre_upgrade_tables
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == HEAD_REVISION
        document_columns = {
            column["name"] for column in sa.inspect(conn).get_columns("document")
        }
        assert {
            "is_syllabus",
            "hidden_from_students",
            "syllabus_document_id",
            "syllabus_unit_number",
        } <= document_columns
        tables = set(sa.inspect(conn).get_table_names())
        assert {"syllabus_draft_unit", "leave_request", "trainer_day_status"} <= tables
    engine.dispose()


def test_upgrade_from_ai194_consent_head_applies_email_outbox_columns(tmp_path):
    """An existing AI-194 head must still run the upstream email migration."""
    cfg, url = _prepare_branch_point(tmp_path, "ai194_consent_head.db")
    command.upgrade(cfg, CONSENT_ATTACHMENTS_MERGE_REVISION)

    engine = sa.create_engine(url)
    message_id = _create_email_outbox_with_sentinel(engine)
    engine.dispose()

    command.upgrade(cfg, "head")

    _assert_email_outbox_migrated(url, message_id)


def test_upgrade_from_upstream_email_head_reaches_merge_head(tmp_path):
    """An existing upstream email head must reach the new merge with data intact."""
    cfg, url = _prepare_branch_point(tmp_path, "upstream_email_head.db")
    command.upgrade(cfg, TICKET_ATTACHMENT_NAMES_REVISION)

    engine = sa.create_engine(url)
    message_id = _create_email_outbox_with_sentinel(engine)
    engine.dispose()

    command.upgrade(cfg, EMAIL_OUTBOX_REVISION)
    command.upgrade(cfg, "head")

    _assert_email_outbox_migrated(url, message_id)


def test_graph_is_a_single_merge_head():
    """The graph must expose exactly one head that joins both feature branches."""
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)

    assert script.get_heads() == [HEAD_REVISION]
    head = script.get_revision(HEAD_REVISION)
    assert head.down_revision == SKILL_BANK_REVISION
    skill_bank = script.get_revision(SKILL_BANK_REVISION)
    assert skill_bank.down_revision == SKILL_TAXONOMY_REVISION
    skill_taxonomy = script.get_revision(SKILL_TAXONOMY_REVISION)
    assert skill_taxonomy.down_revision == EMAIL_MERGE_REVISION
    email_merge = script.get_revision(EMAIL_MERGE_REVISION)
    assert set(email_merge.down_revision) == {
        CONSENT_ATTACHMENTS_MERGE_REVISION,
        EMAIL_OUTBOX_REVISION,
    }
    consent_merge = script.get_revision(CONSENT_ATTACHMENTS_MERGE_REVISION)
    assert set(consent_merge.down_revision) == {
        CHAT_WEB_CONSENT_REVISION,
        TICKET_ATTACHMENT_NAMES_REVISION,
    }
    email_outbox = script.get_revision(EMAIL_OUTBOX_REVISION)
    assert email_outbox.down_revision == TICKET_ATTACHMENT_NAMES_REVISION
    merge = script.get_revision(MERGE_REVISION)
    assert set(merge.down_revision) == {
        SYLLABUS_MERGE_REVISION,
        ADMIN_LEAVE_REVISION,
    }
    for revision in script.walk_revisions():
        assert len(revision.revision) <= 32
