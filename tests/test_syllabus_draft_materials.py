"""AI-166 tests: draft syllabus units and per-unit materials."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.config import settings
from app.core.database import Base, get_session_local, reset_engine
from app.core.deps import get_db
from app.core.seed import seed_database
from app.main import app
from app.models.course import Class
from app.models.document import Document
from app.models.user import User
from app.services import document_service, ingestion_service

SYLLABUS_MARKDOWN = """# Python Course Syllabus

## Topic Outline
Unit 01: Basics
Unit 02: Advanced

## Unit 1: Python Basics
### Session 1
- **Introduction** (90 min)
- Syntax and variables

## Unit 2: Advanced OOP
### Session 2
- **Classes** (120 min)
- Inheritance
"""


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    import app.core.database as dbmod

    reset_engine()
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    monkeypatch.setattr(settings, "email_dry_run", True)
    monkeypatch.setattr(settings, "document_storage_dir", tmp_path)

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
    try:
        seed_database(db)
        yield db
    finally:
        db.close()
        engine.dispose()
    reset_engine()


@pytest.fixture()
def client(db_session, monkeypatch):
    monkeypatch.setattr(ingestion_service, "process_document_in_background", lambda _id: None)

    def _load(path):
        return {"markdown": Path(path).read_text(encoding="utf-8")}

    monkeypatch.setattr(ingestion_service, "_load_document", _load)

    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _headers(client: TestClient, email: str = "teacher@academic.edu.vn", password: str = "Teacher@123"):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _class(db_session) -> Class:
    return db_session.query(Class).filter(Class.code == "CS101-FA26-001").one()


def _teacher(db_session) -> User:
    return db_session.query(User).filter(User.email == "teacher@academic.edu.vn").one()


def _upload(
    client,
    headers,
    class_id,
    name: str,
    content: str,
    *,
    syllabus_document_id: str | None = None,
    unit_number: int | None = None,
):
    data = {"class_id": str(class_id)}
    if syllabus_document_id is not None:
        data["syllabus_document_id"] = syllabus_document_id
    if unit_number is not None:
        data["unit_number"] = str(unit_number)
    return client.post(
        "/api/documents/",
        files=[("files", (name, content.encode(), "text/markdown"))],
        data=data,
        headers=headers,
    )


def _upload_syllabus(client, headers, class_id, name: str = "Syllabus_AI166.md"):
    response = _upload(client, headers, class_id, name, SYLLABUS_MARKDOWN)
    assert response.status_code == 201, response.text
    result = response.json()["uploaded"][0]
    assert result["error"] is None, result
    return result["document"]


def _set_status(db_session, document_id: str, status: str) -> None:
    record = db_session.get(Document, uuid.UUID(document_id))
    record.status = status
    db_session.commit()


def test_upload_syllabus_creates_teacher_draft_without_touching_active_units(client, db_session):
    teacher = _teacher(db_session)
    clazz = _class(db_session)
    headers = _headers(client)

    active = Document(
        id=uuid.uuid4(),
        class_id=clazz.id,
        uploaded_by=teacher.id,
        file_name="Old_Syllabus.md",
        file_type=".md",
        mime_type="text/markdown",
        status="indexed",
        version=1,
    )
    db_session.add(active)
    db_session.commit()
    from app.services.ingestion.syllabus_parser import ParsedSyllabusUnit, SyllabusRoadmapData

    document_service.save_syllabus_roadmap(
        db_session,
        active,
        SyllabusRoadmapData(
            topic_outline="Old outline",
            units=[
                ParsedSyllabusUnit(
                    unit_number=1,
                    unit_title="Old Unit",
                    description=None,
                    content="Old content",
                )
            ],
        ),
    )

    draft = _upload_syllabus(client, headers, clazz.id)
    assert draft["status"] == "pending"

    record = db_session.get(Document, uuid.UUID(draft["id"]))
    assert record.is_syllabus is True
    draft_units = document_service.get_draft_syllabus_units(db_session, record.id)
    assert [unit.unit_number for unit in draft_units] == [1, 2]
    assert [unit.unit_title for unit in draft_units] == ["Python Basics", "Advanced OOP"]

    # The published roadmap must not change while the new syllabus is a draft.
    active_doc, _, active_units = document_service.get_class_syllabus_roadmap(
        db_session, clazz.id
    )
    assert active_doc.id == active.id
    assert [unit.unit_title for unit in active_units] == ["Old Unit"]

    preview = client.get(
        f"/api/documents/classes/{clazz.id}/syllabus-units", headers=headers
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["document_id"] == draft["id"]
    assert body["is_draft"] is True
    assert body["can_approve"] is False
    assert [unit["unit_number"] for unit in body["units"]] == [1, 2]
    assert body["units"][1]["materials"] == []

    # Students see only the active syllabus, never the draft preview.
    student_headers = _headers(client, "student@academic.edu.vn", "Student@123")
    roadmap = client.get(f"/api/student/classes/{clazz.id}/syllabus", headers=student_headers)
    assert roadmap.status_code == 200
    assert [unit["unit_title"] for unit in roadmap.json()["units"]] == ["Old Unit"]
    forbidden = client.get(
        f"/api/documents/classes/{clazz.id}/syllabus-units", headers=student_headers
    )
    assert forbidden.status_code == 403


def test_material_upload_links_units_and_rejects_invalid_targets(client, db_session, monkeypatch):
    clazz = _class(db_session)
    headers = _headers(client)
    draft = _upload_syllabus(client, headers, clazz.id)
    other_class = Class(
        id=uuid.uuid4(),
        trainer_id=_teacher(db_session).id,
        code="CS101-OTHER",
        name="Other class",
        semester="HK1",
        academic_year="2026-2027",
        status="ACTIVE",
    )
    db_session.add(other_class)
    db_session.commit()

    response = _upload(
        client,
        headers,
        clazz.id,
        "notes.md",
        "Useful algorithms notes for unit one.",
        syllabus_document_id=draft["id"],
        unit_number=1,
    )
    assert response.status_code == 201, response.text
    first = response.json()["uploaded"][0]
    assert first["error"] is None, first
    material = db_session.get(Document, uuid.UUID(first["document"]["id"]))
    assert material.syllabus_document_id == uuid.UUID(draft["id"])
    assert material.syllabus_unit_number == 1

    # Multiple materials per unit are allowed.
    second = _upload(
        client,
        headers,
        clazz.id,
        "notes-2.md",
        "More algorithms notes for the same unit.",
        syllabus_document_id=draft["id"],
        unit_number=1,
    )
    assert second.status_code == 201
    assert second.json()["uploaded"][0]["error"] is None
    assert (
        db_session.query(Document)
        .filter(Document.syllabus_document_id == uuid.UUID(draft["id"]))
        .count()
        == 2
    )
    preview = client.get(
        f"/api/documents/classes/{clazz.id}/syllabus-units", headers=headers
    )
    preview_body = preview.json()
    assert preview_body["total_material_count"] == 2
    assert [m["file_name"] for m in preview_body["units"][0]["materials"]] == [
        "notes.md",
        "notes-2.md",
    ]

    wrong_unit = _upload(
        client,
        headers,
        clazz.id,
        "wrong.md",
        "Wrong unit notes.",
        syllabus_document_id=draft["id"],
        unit_number=99,
    )
    assert wrong_unit.json()["uploaded"][0]["error"]

    cross_class = _upload(
        client,
        headers,
        other_class.id,
        "cross.md",
        "Cross class notes.",
        syllabus_document_id=draft["id"],
        unit_number=1,
    )
    assert cross_class.json()["uploaded"][0]["error"]

    syllabus_as_material = _upload(
        client,
        headers,
        clazz.id,
        "Nested_Syllabus.md",
        SYLLABUS_MARKDOWN,
        syllabus_document_id=draft["id"],
        unit_number=1,
    )
    assert syllabus_as_material.json()["uploaded"][0]["error"]
    assert (
        db_session.query(Document)
        .filter(Document.file_name == "Nested_Syllabus.md")
        .first()
        is None
    )


def test_general_upload_binds_current_draft_syllabus_and_stays_private(client, db_session):
    clazz = _class(db_session)
    headers = _headers(client)
    draft = _upload_syllabus(client, headers, clazz.id)

    response = _upload(
        client,
        headers,
        clazz.id,
        "general-notes.md",
        "General material uploaded from the materials table.",
    )
    assert response.status_code == 201, response.text
    uploaded = response.json()["uploaded"][0]
    assert uploaded["error"] is None
    record = db_session.get(Document, uuid.UUID(uploaded["document"]["id"]))
    assert record.syllabus_document_id == uuid.UUID(draft["id"])
    assert record.syllabus_unit_number is None
    assert record.hidden_from_students is True

    _set_status(db_session, uploaded["document"]["id"], "indexed")
    assert document_service.ready_material_count(
        db_session, db_session.get(Document, uuid.UUID(draft["id"]))
    ) == 1
    assert uploaded["document"]["id"] not in document_service.retrievable_document_ids(
        db_session, clazz.id
    )
    student_headers = _headers(client, "student@academic.edu.vn", "Student@123")
    student_docs = client.get(
        f"/api/student/classes/{clazz.id}/documents", headers=student_headers
    ).json()
    assert uploaded["document"]["id"] not in {item["id"] for item in student_docs}

    preview = client.get(
        f"/api/documents/classes/{clazz.id}/syllabus-units", headers=headers
    ).json()
    assert preview["ready_material_count"] == 1
    assert [item["file_name"] for item in preview["syllabus_materials"]] == [
        "general-notes.md"
    ]


def test_attach_existing_indexed_document_to_draft_hides_and_counts(client, db_session):
    clazz = _class(db_session)
    teacher = _teacher(db_session)
    headers = _headers(client)
    draft = _upload_syllabus(client, headers, clazz.id)

    existing = Document(
        id=uuid.uuid4(),
        class_id=clazz.id,
        uploaded_by=teacher.id,
        file_name="Dsa.pdf",
        file_type=".pdf",
        mime_type="application/pdf",
        status="indexed",
        version=1,
    )
    db_session.add(existing)
    db_session.commit()
    assert str(existing.id) in document_service.retrievable_document_ids(
        db_session, clazz.id
    )

    attached = client.post(
        f"/api/documents/{existing.id}/syllabus-link",
        json={"syllabus_document_id": draft["id"]},
        headers=headers,
    )
    assert attached.status_code == 200, attached.text
    assert attached.json()["syllabus_document_id"] == draft["id"]
    assert attached.json()["syllabus_unit_number"] is None

    refreshed = db_session.get(Document, existing.id)
    assert refreshed.hidden_from_students is True
    assert str(existing.id) not in document_service.retrievable_document_ids(
        db_session, clazz.id
    )
    student_headers = _headers(client, "student@academic.edu.vn", "Student@123")
    student_docs = client.get(
        f"/api/student/classes/{clazz.id}/documents", headers=student_headers
    ).json()
    assert str(existing.id) not in {item["id"] for item in student_docs}
    assert document_service.ready_material_count(
        db_session, db_session.get(Document, uuid.UUID(draft["id"]))
    ) == 1

    # A different teacher/student cannot attach, and a document from another
    # class cannot be used as the target.
    student_attach = client.post(
        f"/api/documents/{existing.id}/syllabus-link",
        json={"syllabus_document_id": draft["id"]},
        headers=student_headers,
    )
    assert student_attach.status_code in {401, 403}

    from app.core.security import hash_password
    from app.models.user import Account, Role

    trainer_role = db_session.query(Role).filter(Role.name == "TRAINER").one()
    other_teacher = User(
        full_name="Other Trainer",
        email="other-teacher@example.com",
        role_id=trainer_role.id,
        status="ACTIVE",
    )
    db_session.add(other_teacher)
    db_session.flush()
    db_session.add(
        Account(
            user_id=other_teacher.id,
            password_hash=hash_password("Other@123"),
            is_active=True,
        )
    )
    db_session.commit()
    other_headers = _headers(client, "other-teacher@example.com", "Other@123")
    other_attach = client.post(
        f"/api/documents/{existing.id}/syllabus-link",
        json={"syllabus_document_id": draft["id"]},
        headers=other_headers,
    )
    assert other_attach.status_code == 403

    other_class = Class(
        id=uuid.uuid4(),
        trainer_id=teacher.id,
        code="CS101-ATTACH-OTHER",
        name="Attach other class",
        semester="HK1",
        academic_year="2026-2027",
        status="ACTIVE",
    )
    db_session.add(other_class)
    db_session.commit()
    other_syllabus = _upload_syllabus(
        client, headers, other_class.id, "Syllabus_Attach_Other.md"
    )
    cross_target = client.post(
        f"/api/documents/{existing.id}/syllabus-link",
        json={"syllabus_document_id": other_syllabus["id"]},
        headers=headers,
    )
    assert cross_target.status_code == 400


def test_syllabus_approval_requires_one_indexed_material_anywhere(client, db_session):
    clazz = _class(db_session)
    headers = _headers(client)
    draft = _upload_syllabus(client, headers, clazz.id)

    material = _upload(
        client,
        headers,
        clazz.id,
        "unit-one.md",
        "Unit one notes.",
        syllabus_document_id=draft["id"],
        unit_number=1,
    ).json()["uploaded"][0]["document"]

    # Unit 2 is empty; approval is still blocked until one material is indexed.
    blocked = client.post(f"/api/documents/{draft['id']}/approve", headers=headers)
    assert blocked.status_code == 400
    assert "at least one ready material" in blocked.json()["detail"].lower()
    assert db_session.get(Document, uuid.UUID(draft["id"])).status == "pending"

    _set_status(db_session, material["id"], "processing")
    still_blocked = client.post(f"/api/documents/{draft['id']}/approve", headers=headers)
    assert still_blocked.status_code == 400

    _set_status(db_session, material["id"], "failed")
    failed_blocked = client.post(f"/api/documents/{draft['id']}/approve", headers=headers)
    assert failed_blocked.status_code == 400

    _set_status(db_session, material["id"], "replaced")
    replaced_blocked = client.post(f"/api/documents/{draft['id']}/approve", headers=headers)
    assert replaced_blocked.status_code == 400

    _set_status(db_session, material["id"], "indexed")
    approved = client.post(f"/api/documents/{draft['id']}/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "processing"


def test_material_can_be_added_after_syllabus_approval(client, db_session):
    clazz = _class(db_session)
    headers = _headers(client)
    draft = _upload_syllabus(client, headers, clazz.id)
    _set_status(db_session, draft["id"], "indexed")

    from app.services.ingestion.syllabus_parser import parse_syllabus_markdown

    record = db_session.get(Document, uuid.UUID(draft["id"]))
    document_service.replace_syllabus_roadmap(
        db_session, record, parse_syllabus_markdown(SYLLABUS_MARKDOWN)
    )

    response = _upload(
        client,
        headers,
        clazz.id,
        "after-approval.md",
        "Material added after approval.",
        syllabus_document_id=draft["id"],
        unit_number=2,
    )
    assert response.status_code == 201, response.text
    material = response.json()["uploaded"][0]
    assert material["error"] is None
    linked = db_session.get(Document, uuid.UUID(material["document"]["id"]))
    assert linked.syllabus_unit_number == 2


def test_draft_linked_material_is_hidden_from_student_until_syllabus_is_indexed(client, db_session):
    clazz = _class(db_session)
    headers = _headers(client)
    draft = _upload_syllabus(client, headers, clazz.id)
    material = _upload(
        client,
        headers,
        clazz.id,
        "draft-material.md",
        "Draft material notes.",
        syllabus_document_id=draft["id"],
        unit_number=1,
    ).json()["uploaded"][0]["document"]
    _set_status(db_session, material["id"], "indexed")

    allowed = document_service.retrievable_document_ids(db_session, clazz.id)
    assert material["id"] not in allowed

    student_headers = _headers(client, "student@academic.edu.vn", "Student@123")
    student_docs = client.get(
        f"/api/student/classes/{clazz.id}/documents", headers=student_headers
    )
    assert student_docs.status_code == 200
    assert material["id"] not in {item["id"] for item in student_docs.json()}

    _set_status(db_session, draft["id"], "indexed")
    allowed_after = document_service.retrievable_document_ids(db_session, clazz.id)
    assert material["id"] in allowed_after


def test_delete_draft_syllabus_clears_material_links_without_touching_active_units(client, db_session):
    clazz = _class(db_session)
    headers = _headers(client)
    draft = _upload_syllabus(client, headers, clazz.id)
    material = _upload(
        client,
        headers,
        clazz.id,
        "to-unlink.md",
        "Material to unlink.",
        syllabus_document_id=draft["id"],
        unit_number=1,
    ).json()["uploaded"][0]["document"]

    deleted = client.delete(
        f"/api/documents/{draft['id']}", params={"confirm": "true"}, headers=headers
    )
    assert deleted.status_code == 200, deleted.text

    linked = db_session.get(Document, uuid.UUID(material["id"]))
    assert linked is not None
    assert linked.syllabus_document_id is None
    assert linked.syllabus_unit_number is None
    assert document_service.get_draft_syllabus_units(db_session, draft["id"]) == []


def _upload_batch(client, headers, class_id, files: list[tuple[str, str]]):
    return client.post(
        "/api/documents/",
        files=[
            ("files", (name, content.encode(), "text/markdown"))
            for name, content in files
        ],
        data={"class_id": str(class_id)},
        headers=headers,
    )


def _result_by_name(body: dict, name: str) -> dict:
    return next(item for item in body["uploaded"] if item["file_name"] == name)


def test_batch_syllabus_then_material_binds_new_draft(client, db_session):
    clazz = _class(db_session)
    headers = _headers(client)
    response = _upload_batch(
        client,
        headers,
        clazz.id,
        [
            ("Syllabus_Batch.md", SYLLABUS_MARKDOWN),
            ("batch-material.md", "Generic batch material."),
        ],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    syllabus = _result_by_name(body, "Syllabus_Batch.md")["document"]
    material = _result_by_name(body, "batch-material.md")["document"]
    record = db_session.get(Document, uuid.UUID(material["id"]))
    assert record.syllabus_document_id == uuid.UUID(syllabus["id"])
    assert record.syllabus_unit_number is None
    assert record.hidden_from_students is True
    _set_status(db_session, material["id"], "indexed")
    assert document_service.ready_material_count(
        db_session, db_session.get(Document, uuid.UUID(syllabus["id"]))
    ) == 1


def test_batch_reverse_order_material_and_syllabus_is_deterministic(client, db_session):
    clazz = _class(db_session)
    headers = _headers(client)
    response = _upload_batch(
        client,
        headers,
        clazz.id,
        [
            ("reverse-material.md", "Generic reverse material."),
            ("Syllabus_Reverse.md", SYLLABUS_MARKDOWN),
        ],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    syllabus = _result_by_name(body, "Syllabus_Reverse.md")["document"]
    material = _result_by_name(body, "reverse-material.md")["document"]
    record = db_session.get(Document, uuid.UUID(material["id"]))
    assert record.syllabus_document_id == uuid.UUID(syllabus["id"])
    assert record.syllabus_unit_number is None
    assert record.hidden_from_students is True


def test_batch_new_draft_takes_precedence_over_existing_active_syllabus(client, db_session):
    clazz = _class(db_session)
    teacher = _teacher(db_session)
    headers = _headers(client)
    active = Document(
        id=uuid.uuid4(),
        class_id=clazz.id,
        uploaded_by=teacher.id,
        file_name="Old_Active_Syllabus.md",
        file_type=".md",
        mime_type="text/markdown",
        status="indexed",
        version=1,
    )
    db_session.add(active)
    db_session.commit()
    from app.services.ingestion.syllabus_parser import ParsedSyllabusUnit, SyllabusRoadmapData

    document_service.save_syllabus_roadmap(
        db_session,
        active,
        SyllabusRoadmapData(
            topic_outline="Old outline",
            units=[
                ParsedSyllabusUnit(
                    unit_number=1,
                    unit_title="Old Active Unit",
                    description=None,
                    content="Old active content",
                )
            ],
        ),
    )
    response = _upload_batch(
        client,
        headers,
        clazz.id,
        [
            ("New_Draft_Syllabus.md", SYLLABUS_MARKDOWN),
            ("new-draft-material.md", "Generic new draft material."),
        ],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    new_syllabus = _result_by_name(body, "New_Draft_Syllabus.md")["document"]
    material = _result_by_name(body, "new-draft-material.md")["document"]
    record = db_session.get(Document, uuid.UUID(material["id"]))
    assert record.syllabus_document_id == uuid.UUID(new_syllabus["id"])
    assert record.hidden_from_students is True
    active_doc, _, active_units = document_service.get_class_syllabus_roadmap(
        db_session, clazz.id
    )
    assert active_doc.id == active.id
    assert [unit.unit_title for unit in active_units] == ["Old Active Unit"]


def test_batch_with_multiple_syllabi_rejects_without_leaking_material(client, db_session):
    clazz = _class(db_session)
    headers = _headers(client)
    response = _upload_batch(
        client,
        headers,
        clazz.id,
        [
            ("Syllabus_First.md", SYLLABUS_MARKDOWN),
            ("Syllabus_Second.md", SYLLABUS_MARKDOWN),
            ("ambiguous-material.md", "Generic ambiguous material."),
        ],
    )
    assert response.status_code == 400
    names = {
        name
        for (name,) in db_session.query(Document.file_name).all()
        if name in {"Syllabus_First.md", "Syllabus_Second.md", "ambiguous-material.md"}
    }
    assert names == set()


def test_force_upload_detects_syllabus_from_content_headers(client, db_session):
    clazz = _class(db_session)
    headers = _headers(client)

    response = client.post(
        "/api/documents/?force=true",
        files=[("files", ("notes.md", SYLLABUS_MARKDOWN.encode(), "text/markdown"))],
        data={"class_id": str(clazz.id)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    uploaded = response.json()["uploaded"][0]
    assert uploaded["error"] is None, uploaded
    document_id = uploaded["document"]["id"]
    record = db_session.get(Document, uuid.UUID(document_id))
    assert record.is_syllabus is True
    assert len(document_service.get_draft_syllabus_units(db_session, document_id)) == 2

    blocked = client.post(f"/api/documents/{document_id}/approve", headers=headers)
    assert blocked.status_code == 400
    assert "at least one ready material" in blocked.json()["detail"].lower()


def test_delete_draft_does_not_publish_linked_indexed_material(client, db_session):
    clazz = _class(db_session)
    teacher = _teacher(db_session)
    headers = _headers(client)

    active = Document(
        id=uuid.uuid4(),
        class_id=clazz.id,
        uploaded_by=teacher.id,
        file_name="Active_Syllabus.md",
        file_type=".md",
        mime_type="text/markdown",
        status="indexed",
        version=1,
    )
    active_material = Document(
        id=uuid.uuid4(),
        class_id=clazz.id,
        uploaded_by=teacher.id,
        file_name="active-material.md",
        file_type=".md",
        mime_type="text/markdown",
        status="indexed",
        version=1,
    )
    db_session.add_all([active, active_material])
    db_session.commit()
    from app.services.ingestion.syllabus_parser import ParsedSyllabusUnit, SyllabusRoadmapData

    document_service.save_syllabus_roadmap(
        db_session,
        active,
        SyllabusRoadmapData(
            topic_outline="Active outline",
            units=[
                ParsedSyllabusUnit(
                    unit_number=1,
                    unit_title="Active Unit",
                    description=None,
                    content="Active content",
                )
            ],
        ),
    )

    draft = _upload_syllabus(client, headers, clazz.id, "Syllabus_Delete_Privacy.md")
    material = _upload(
        client,
        headers,
        clazz.id,
        "draft-private.md",
        "Private draft material.",
        syllabus_document_id=draft["id"],
        unit_number=1,
    ).json()["uploaded"][0]["document"]
    _set_status(db_session, material["id"], "indexed")

    assert material["id"] not in document_service.retrievable_document_ids(
        db_session, clazz.id
    )
    student_headers = _headers(client, "student@academic.edu.vn", "Student@123")
    before = client.get(
        f"/api/student/classes/{clazz.id}/documents", headers=student_headers
    ).json()
    assert material["id"] not in {item["id"] for item in before}
    assert str(active_material.id) in {item["id"] for item in before}

    deleted = client.delete(
        f"/api/documents/{draft['id']}", params={"confirm": "true"}, headers=headers
    )
    assert deleted.status_code == 200, deleted.text

    allowed_after = document_service.retrievable_document_ids(db_session, clazz.id)
    assert material["id"] not in allowed_after
    after = client.get(
        f"/api/student/classes/{clazz.id}/documents", headers=student_headers
    ).json()
    after_ids = {item["id"] for item in after}
    assert material["id"] not in after_ids
    assert str(active_material.id) in after_ids
    assert str(active.id) in after_ids
    assert str(active_material.id) in allowed_after
    _, _, active_units = document_service.get_class_syllabus_roadmap(
        db_session, clazz.id
    )
    assert [unit.unit_title for unit in active_units] == ["Active Unit"]


def test_reupload_draft_keeps_active_units_and_latest_preview(client, db_session):
    clazz = _class(db_session)
    teacher = _teacher(db_session)
    headers = _headers(client)

    active = Document(
        id=uuid.uuid4(),
        class_id=clazz.id,
        uploaded_by=teacher.id,
        file_name="Active_Syllabus.md",
        file_type=".md",
        mime_type="text/markdown",
        status="indexed",
        version=1,
    )
    db_session.add(active)
    db_session.commit()
    from app.services.ingestion.syllabus_parser import ParsedSyllabusUnit, SyllabusRoadmapData

    document_service.save_syllabus_roadmap(
        db_session,
        active,
        SyllabusRoadmapData(
            topic_outline="Active outline",
            units=[
                ParsedSyllabusUnit(
                    unit_number=1,
                    unit_title="Active Unit",
                    description=None,
                    content="Active content",
                )
            ],
        ),
    )

    first = _upload_syllabus(client, headers, clazz.id, "Syllabus_Reupload.md")
    second = _upload_syllabus(client, headers, clazz.id, "Syllabus_Reupload.md")
    assert first["id"] != second["id"]

    _, _, active_units = document_service.get_class_syllabus_roadmap(
        db_session, clazz.id
    )
    assert [unit.unit_title for unit in active_units] == ["Active Unit"]

    preview = client.get(
        f"/api/documents/classes/{clazz.id}/syllabus-units", headers=headers
    )
    assert preview.status_code == 200
    assert preview.json()["document_id"] == second["id"]
    assert [unit["unit_number"] for unit in preview.json()["units"]] == [1, 2]


def test_teacher_syllabus_and_unit_upload(client, db_session):
    headers = _headers(client)
    clazz = _class(db_session)

    syllabus = _upload_syllabus(client, headers, clazz.id, "Syllabus_NoAI.md")
    assert syllabus["status"] == "pending"

    response = _upload(
        client,
        headers,
        clazz.id,
        "unit-note.md",
        "Unit one supporting note.",
        syllabus_document_id=syllabus["id"],
        unit_number=1,
    )
    assert response.status_code == 201, response.text
    result = response.json()["uploaded"][0]
    assert result["error"] is None, result
    assert result["document"]["status"] == "pending"

    record = db_session.get(Document, uuid.UUID(result["document"]["id"]))
    assert record is not None
    assert str(record.syllabus_document_id) == syllabus["id"]
    assert record.syllabus_unit_number == 1


def test_teacher_invalid_syllabus_still_rejected(client, db_session):
    headers = _headers(client)
    clazz = _class(db_session)

    response = _upload(
        client,
        headers,
        clazz.id,
        "Broken_Syllabus.md",
        "# Broken syllabus\n\nNo course units here.",
    )

    assert response.status_code == 201, response.text
    result = response.json()["uploaded"][0]
    assert result["document"] is None
    assert "Syllabus format is not recognized" in (result["error"] or "")


def test_migration_merge_upgrade_and_downgrade(tmp_path):
    from alembic.config import Config

    from alembic import command

    test_db = tmp_path / "syllabus_draft_migration.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{test_db}")

    engine = create_engine(f"sqlite:///{test_db}")
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE "class" (id CHAR(32) PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE "document" (id CHAR(32) PRIMARY KEY)'))
        # 0047_admin_leave extends the leave table created by 0046_absence;
        # the minimal row keeps that upstream branch upgradeable in this
        # syllabus-focused SQLite fixture.
        conn.execute(
            text(
                'CREATE TABLE "leave_request" ('
                "id CHAR(32) PRIMARY KEY, target_trainer_id CHAR(32), reason TEXT)"
            )
        )
        # 0053/0054/0055 touch the skill taxonomy and chat-session tables that
        # predate this branch point; recreate their pre-0053 shape so this
        # SQLite fixture can reach head.
        conn.execute(
            text(
                'CREATE TABLE "skill" ('
                "id CHAR(32) PRIMARY KEY, class_id CHAR(32), "
                "code VARCHAR(100) NOT NULL, name VARCHAR(255) NOT NULL, "
                "category VARCHAR(100) NOT NULL DEFAULT 'GENERAL', description TEXT, "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            )
        )
        conn.execute(
            text(
                'CREATE TABLE "skill_level_rubric" ('
                "id CHAR(32) PRIMARY KEY, skill_id CHAR(32) NOT NULL, "
                "level VARCHAR(20) NOT NULL, description TEXT NOT NULL, "
                "threshold_pct INTEGER NOT NULL DEFAULT 70, "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            )
        )
        conn.execute(
            text(
                'CREATE TABLE "chat_session" ('
                "id CHAR(32) PRIMARY KEY, user_id CHAR(32), "
                "is_pinned BOOLEAN NOT NULL DEFAULT 0, updated_at DATETIME, "
                "pinned_at DATETIME)"
            )
        )
    engine.dispose()

    command.stamp(cfg, "0046_absence_handover")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{test_db}")
    tables = set(inspect(engine).get_table_names())
    columns = {column["name"] for column in inspect(engine).get_columns("document")}
    assert "syllabus_draft_unit" in tables
    assert {
        "is_syllabus",
        "hidden_from_students",
        "syllabus_document_id",
        "syllabus_unit_number",
    } <= columns
    engine.dispose()

    command.downgrade(cfg, "0040_quiz_validation")
    engine = create_engine(f"sqlite:///{test_db}")
    tables_after = set(inspect(engine).get_table_names())
    columns_after = {column["name"] for column in inspect(engine).get_columns("document")}
    assert "syllabus_draft_unit" not in tables_after
    assert "syllabus_document_id" not in columns_after
    assert "hidden_from_students" not in columns_after
    engine.dispose()
