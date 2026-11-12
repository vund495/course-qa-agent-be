"""Holiday calendar API authorization, scopes, and validation."""

import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core.database import Base
from app.core.deps import get_current_user, get_db
from app.models.attendance import Holiday
from app.models.course import Class, Enrollment
from app.models.user import Role, User


@pytest.fixture()
def calendar():
    from app.routers import holidays

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as db:
        users = {}
        for role_name in ("ADMIN", "TRAINER", "STUDENT"):
            role = Role(name=role_name)
            db.add(role)
            db.flush()
            user = User(
                email=f"{role_name}@calendar.test",
                full_name=role_name,
                role_id=role.id,
                status="ACTIVE",
            )
            db.add(user)
            db.flush()
            users[role_name] = user
        clazz = Class(
            code="HOL-1",
            name="Calendar class",
            trainer_id=users["TRAINER"].id,
            status="ACTIVE",
            semester="HK1",
            academic_year="2026",
            credits=3,
        )
        db.add(clazz)
        db.flush()
        db.add(Enrollment(class_id=clazz.id, student_id=users["STUDENT"].id, status="ACTIVE"))
        db.commit()
        app = FastAPI()
        app.include_router(holidays.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db
        actor = {"user": users["ADMIN"]}
        app.dependency_overrides[get_current_user] = lambda: actor["user"]
        with TestClient(app) as client:
            yield client, db, users, clazz, actor
    engine.dispose()


def test_admin_crud_filters_by_year_and_reports_conflicts(calendar):
    client, db, _, clazz, _ = calendar
    payload = {"date": "2026-11-12", "name": "  Day off  ", "scope": "system"}
    created = client.post("/api/admin/holidays", json=payload)
    assert created.status_code == 201
    row = created.json()
    assert row["name"] == "Day off"
    assert row["type"] == "admin"
    assert client.post("/api/admin/holidays", json=payload).status_code == 409
    assert client.get("/api/admin/holidays?year=2027").json() == []
    assert client.get("/api/admin/holidays?year=2026").json() == [row]
    changed = client.put(
        f"/api/admin/holidays/{row['id']}",
        json={**payload, "name": "Class day", "scope": "class", "class_id": str(clazz.id)},
    )
    assert changed.status_code == 200
    assert changed.json()["scope"] == "class"
    assert client.delete(f"/api/admin/holidays/{row['id']}").status_code == 204
    assert db.get(Holiday, uuid.UUID(row["id"])) is None
    assert client.delete(f"/api/admin/holidays/{row['id']}").status_code == 404


def test_calendar_read_scopes_and_admin_write_guard(calendar):
    client, db, users, clazz, actor = calendar
    db.add_all(
        [
            Holiday(date=date(2026, 11, 12), name="System", scope="system", type="admin"),
            Holiday(
                date=date(2026, 11, 13),
                name="Class",
                scope="class",
                class_id=clazz.id,
                type="admin",
            ),
            Holiday(
                date=date(2026, 11, 14),
                name="Other",
                scope="class",
                class_id=uuid.uuid4(),
                type="admin",
            ),
        ]
    )
    db.commit()
    actor["user"] = users["STUDENT"]
    assert client.get("/api/admin/holidays?year=2026").status_code == 403
    assert (
        client.post("/api/admin/holidays", json={"date": "2026-11-15", "name": "No"}).status_code
        == 403
    )
    response = client.get(f"/api/classes/{clazz.id}/holidays?year=2026")
    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == ["System", "Class"]
    db.query(Enrollment).delete()
    db.commit()
    assert client.get(f"/api/classes/{clazz.id}/holidays?year=2026").status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"scope": "class"},
        {"scope": "system", "class_id": "00000000-0000-0000-0000-000000000001"},
    ],
)
def test_calendar_validates_scope_and_names(calendar, changes):
    client, _, _, _, _ = calendar
    response = client.post(
        "/api/admin/holidays", json={"date": "2026-11-12", "name": "Holiday", **changes}
    )
    assert response.status_code == 422


def test_non_admin_cannot_update_or_delete_holidays(calendar):
    client, _, users, _, actor = calendar
    payload = {"date": "2026-11-12", "name": "Protected"}
    created = client.post("/api/admin/holidays", json=payload).json()
    for role in ("TRAINER", "STUDENT"):
        actor["user"] = users[role]
        path = f"/api/admin/holidays/{created['id']}"
        assert client.put(path, json=payload).status_code == 403
        assert client.delete(path).status_code == 403


def test_calendar_rejects_missing_classes_and_invalid_years(calendar):
    client, _, _, _, _ = calendar
    assert (
        client.post(
            "/api/admin/holidays",
            json={
                "date": "2026-11-12",
                "name": "Class off",
                "scope": "class",
                "class_id": str(uuid.uuid4()),
            },
        ).status_code
        == 404
    )
    assert client.get("/api/admin/holidays?year=0").status_code == 422
    assert client.get("/api/admin/holidays?year=10000").status_code == 422
