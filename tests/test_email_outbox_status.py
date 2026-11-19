"""AI-138: the outbox must report what really happened to each message.

The defect this covers: ``_send_one`` returned early on a dry run, but the
caller still wrote ``sent`` and ``sent_at``, so the admin saw a green Sent
status for mail that was never transmitted.
"""

from __future__ import annotations

import smtplib

import pytest
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (register tables)
from app.config import settings
from app.core.database import Base, get_session_local, reset_engine
from app.models.email_outbox import (
    EMAIL_DRY_RUN,
    EMAIL_FAILED,
    EMAIL_SENT,
    EmailOutbox,
)
from app.services import email_service

TEST_DB_URL = "sqlite://"


@pytest.fixture()
def db_session(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.core.database as dbmod

    reset_engine()
    monkeypatch.setattr(settings, "database_url", TEST_DB_URL)

    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    dbmod._engine = engine
    dbmod._SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod._db_url = TEST_DB_URL
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_session_local(TEST_DB_URL)
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
    reset_engine()


@pytest.fixture(autouse=True)
def _reset_drain_state():
    email_service._DRAIN_STATE.update(
        draining=False, started_at=None, total=0, done=0, sent=0, failed=0
    )
    yield
    email_service._DRAIN_STATE.update(
        draining=False, started_at=None, total=0, done=0, sent=0, failed=0
    )


def _queue_one(db: Session) -> EmailOutbox:
    return email_service.queue_email(db, "student@example.com", "Subject", "Body")


def _config(dry_run: bool):
    return lambda db: {"smtp_rate_per_minute": 60, "email_dry_run": dry_run}


def test_dry_run_does_not_mark_sent(db_session: Session, monkeypatch):
    entry = _queue_one(db_session)
    monkeypatch.setattr(email_service, "effective_email_config", _config(True))
    monkeypatch.setattr(email_service, "_smtp_credentials", lambda db: ("host", 1, "s", "pw"))

    email_service.process_queue(db_session, sleep_between=False)

    db_session.refresh(entry)
    assert entry.status == EMAIL_DRY_RUN
    assert entry.status != EMAIL_SENT
    assert entry.sent_at is None
    assert entry.last_attempt_at is not None


def test_smtp_rejection_marks_failed_with_error(db_session: Session, monkeypatch):
    entry = _queue_one(db_session)
    monkeypatch.setattr(email_service, "effective_email_config", _config(False))
    monkeypatch.setattr(email_service, "_smtp_credentials", lambda db: ("host", 1, "s", "pw"))

    def reject(*args, **kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(email_service, "_send_one", reject)

    email_service.process_queue(db_session, sleep_between=False)

    db_session.refresh(entry)
    assert entry.status == EMAIL_FAILED
    assert "bad credentials" in entry.last_error
    assert entry.failed_at is not None
    assert entry.sent_at is None


def test_smtp_success_marks_sent_with_timestamp(db_session: Session, monkeypatch):
    entry = _queue_one(db_session)
    monkeypatch.setattr(email_service, "effective_email_config", _config(False))
    monkeypatch.setattr(email_service, "_smtp_credentials", lambda db: ("host", 1, "s", "pw"))
    monkeypatch.setattr(email_service, "_send_one", lambda *a, **k: True)

    email_service.process_queue(db_session, sleep_between=False)

    db_session.refresh(entry)
    assert entry.status == EMAIL_SENT
    assert entry.sent_at is not None
    assert entry.failed_at is None
    assert entry.last_error == ""


def test_stats_count_dry_run_apart_from_sent(db_session: Session, monkeypatch):
    _queue_one(db_session)
    monkeypatch.setattr(email_service, "effective_email_config", _config(True))
    monkeypatch.setattr(email_service, "_smtp_credentials", lambda db: ("host", 1, "s", "pw"))

    email_service.process_queue(db_session, sleep_between=False)

    stats = email_service.queue_stats(db_session)
    assert stats["dry_run"] == 1
    assert stats["sent"] == 0
