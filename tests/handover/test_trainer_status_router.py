"""Integration tests for trainer day-status router."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.config import settings
from app.core.database import Base, get_session_local, reset_engine
from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.course import Class, ClassTrainer
from app.models.user import Role, User
from app.services.holiday_service import VIETNAM_TZ, local_date

TODAY = local_date(datetime.now(VIETNAM_TZ))
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)
TOO_OLD = TODAY - timedelta(days=10)


@pytest.fixture()
def db_session(monkeypatch) -> Generator[Session, None, None]:
    """In-memory SQLite database with users, a class, and a co-trainer."""
    monkeypatch.setattr("app.services.reranker_service.warm_up", lambda: None)

    import app.core.database as dbmod

    reset_engine()
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    dbmod._engine = engine
    dbmod._SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod._db_url = "sqlite://"
    Base.metadata.create_all(bind=engine)

    db = get_session_local("sqlite://")()

    admin_role = Role(name="ADMIN")
    trainer_role = Role(name="TRAINER")
    student_role = Role(name="STUDENT")
    db.add_all([admin_role, trainer_role, student_role])
    db.flush()

    admin = User(
        full_name="Admin User",
        email="admin@handover.test",
        role_id=admin_role.id,
        status="ACTIVE",
    )
    primary = User(
        full_name="Primary Trainer",
        email="primary@handover.test",
        role_id=trainer_role.id,
        status="ACTIVE",
    )
    co_trainer = User(
        full_name="Co Trainer",
        email="co@handover.test",
        role_id=trainer_role.id,
        status="ACTIVE",
    )
    other_trainer = User(
        full_name="Other Trainer",
        email="other@handover.test",
        role_id=trainer_role.id,
        status="ACTIVE",
    )
    student = User(
        full_name="Student User",
        email="student@handover.test",
        role_id=student_role.id,
        status="ACTIVE",
    )
    db.add_all([admin, primary, co_trainer, other_trainer, student])
    db.flush()

    clazz = Class(
        code="AI158-ROUTER-01",
        name="AI-158 Router Class",
        trainer_id=primary.id,
        semester="HK1",
        academic_year="2026-2027",
        status="ACTIVE",
        credits=3,
    )
    db.add(clazz)
    db.flush()
    db.add(ClassTrainer(class_id=clazz.id, trainer_id=co_trainer.id))
    db.commit()

    db.info.update(
        admin_id=admin.id,
        primary_id=primary.id,
        co_trainer_id=co_trainer.id,
        other_trainer_id=other_trainer.id,
        student_id=student.id,
        class_id=clazz.id,
    )
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
        reset_engine()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _headers(user_id: uuid.UUID, role: str) -> dict[str, str]:
    token = create_access_token(str(user_id), role)
    return {"Authorization": f"Bearer {token}"}


def _trainer_headers(db_session: Session) -> dict[str, str]:
    return _headers(db_session.info["primary_id"], "trainer")


def _admin_headers(db_session: Session) -> dict[str, str]:
    return _headers(db_session.info["admin_id"], "admin")


def test_trainer_status_defaults_to_present(client: TestClient, db_session: Session):
    headers = _trainer_headers(db_session)

    res = client.get("/api/trainer-status", headers=headers)

    assert res.status_code == 200
    body = res.json()
    assert body["trainer_id"] == str(db_session.info["primary_id"])
    assert body["trainer_name"] == "Primary Trainer"
    assert body["date"] == TODAY.isoformat()
    assert body["status"] == "present"
    assert body["note"] is None
    assert body["recorded_by"] is None
    assert body["updated_at"] is None


def test_trainer_status_put_roundtrip_and_validation(client: TestClient, db_session: Session):
    headers = _trainer_headers(db_session)

    res = client.put(
        "/api/trainer-status",
        json={"status": "off", "note": "  sick  "},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "off"
    assert body["note"] == "sick"
    assert body["date"] == TODAY.isoformat()
    assert body["recorded_by"] == str(db_session.info["primary_id"])

    res = client.get("/api/trainer-status", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "off"

    res = client.put(
        "/api/trainer-status",
        json={"status": "present", "date": YESTERDAY.isoformat()},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["date"] == YESTERDAY.isoformat()

    res = client.put(
        "/api/trainer-status",
        json={"status": "off", "date": TOO_OLD.isoformat()},
        headers=headers,
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Only the last 7 days can be marked."

    res = client.put(
        "/api/trainer-status",
        json={"status": "off", "date": TOMORROW.isoformat()},
        headers=headers,
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Date cannot be in the future."

    res = client.put(
        "/api/trainer-status",
        json={"status": "vacation"},
        headers=headers,
    )
    assert res.status_code == 422


def test_trainer_status_permissions_and_admin_override(
    client: TestClient, db_session: Session
):
    student_headers = _headers(db_session.info["student_id"], "student")
    other_headers = _headers(db_session.info["other_trainer_id"], "trainer")
    admin_headers = _admin_headers(db_session)

    assert client.get("/api/trainer-status", headers=student_headers).status_code == 403
    assert (
        client.put(
            "/api/trainer-status",
            json={"status": "off"},
            headers=student_headers,
        ).status_code
        == 403
    )

    assert (
        client.put(
            "/api/trainer-status",
            json={
                "trainer_id": str(db_session.info["primary_id"]),
                "status": "off",
            },
            headers=other_headers,
        ).status_code
        == 403
    )

    res = client.put(
        "/api/trainer-status",
        json={
            "trainer_id": str(db_session.info["primary_id"]),
            "status": "off",
            "note": "admin override",
        },
        headers=admin_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["trainer_id"] == str(db_session.info["primary_id"])
    assert body["status"] == "off"
    assert body["note"] == "admin override"
    assert body["recorded_by"] == str(db_session.info["admin_id"])

    res = client.put(
        "/api/trainer-status",
        json={"trainer_id": str(uuid.uuid4()), "status": "off"},
        headers=admin_headers,
    )
    assert res.status_code == 404


def test_class_trainer_status_permissions_and_defaults(
    client: TestClient, db_session: Session
):
    class_id = db_session.info["class_id"]
    primary_headers = _trainer_headers(db_session)
    co_headers = _headers(db_session.info["co_trainer_id"], "trainer")
    other_headers = _headers(db_session.info["other_trainer_id"], "trainer")
    student_headers = _headers(db_session.info["student_id"], "student")
    admin_headers = _admin_headers(db_session)

    res = client.get(f"/api/classes/{class_id}/trainer-status", headers=primary_headers)
    assert res.status_code == 200
    rows = {row["trainer_id"]: row for row in res.json()}
    assert rows[str(db_session.info["primary_id"])]["status"] == "present"
    assert rows[str(db_session.info["co_trainer_id"])]["status"] == "present"

    assert (
        client.get(f"/api/classes/{class_id}/trainer-status", headers=co_headers).status_code
        == 200
    )
    assert (
        client.get(f"/api/classes/{class_id}/trainer-status", headers=admin_headers).status_code
        == 200
    )
    assert (
        client.get(f"/api/classes/{class_id}/trainer-status", headers=other_headers).status_code
        == 403
    )
    assert (
        client.get(f"/api/classes/{class_id}/trainer-status", headers=student_headers).status_code
        == 403
    )

    client.put(
        "/api/trainer-status",
        json={"status": "off"},
        headers=co_headers,
    )
    res = client.get(
        f"/api/classes/{class_id}/trainer-status?date={TODAY.isoformat()}",
        headers=primary_headers,
    )
    assert res.status_code == 200
    rows = {row["trainer_id"]: row for row in res.json()}
    assert rows[str(db_session.info["primary_id"])]["status"] == "present"
    assert rows[str(db_session.info["co_trainer_id"])]["status"] == "off"

    res = client.get(
        f"/api/classes/{uuid.uuid4()}/trainer-status",
        headers=admin_headers,
    )
    assert res.status_code == 404


def test_trainer_status_requires_authentication(client: TestClient):
    assert client.get("/api/trainer-status").status_code == 401
    assert client.put("/api/trainer-status", json={"status": "off"}).status_code == 401
