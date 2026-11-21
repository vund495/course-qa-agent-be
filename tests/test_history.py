"""Tests for Chat History endpoints and service (AI-95, Epic E7).

Covers AC-01 through AC-07:
- AC-01, AC-02, AC-03: save_chat_turn and message persistence
- AC-04, AC-06: GET /api/history list sessions, sorted updated_at DESC
- AC-05, AC-07: GET /api/history/{session_id} transcript, ordered created_at ASC
- Row-level security: 403 Forbidden when accessing another user's session
- Cascade deletion: DELETE /api/history/{session_id}
"""

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database as dbmod
from app import models  # noqa: F401
from app.config import settings
from app.core.database import Base, get_session_local, reset_engine
from app.core.deps import get_db
from app.core.seed import seed_database
from app.main import app
from app.models.chat import ChatMessage, ChatSession
from app.models.course import Class
from app.models.user import User
from app.services import history_service

TEST_DB_URL = "sqlite://"


@pytest.fixture()
def db_session(monkeypatch: pytest.MonkeyPatch) -> Generator[Session, None, None]:
    """Provides an isolated in-memory SQLite session with all tables created."""
    reset_engine()
    monkeypatch.setattr(settings, "database_url", TEST_DB_URL)
    monkeypatch.setattr(settings, "email_dry_run", True)

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
        seed_database(db)
        # Standalone test class (no course binding).
        trainer = db.query(User).filter(User.email == "teacher@academic.edu.vn").first()
        test_class = Class(
            trainer_id=trainer.id,
            code="CS101-A",
            name="Class A",
            semester="1",
            academic_year="2026-2027",
        )
        db.add(test_class)
        db.commit()

        yield db
    finally:
        db.close()
        engine.dispose()
        reset_engine()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with overridden get_db dependency."""

    def _override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _get_test_class_id(db_session: Session) -> uuid.UUID:
    clazz = db_session.query(Class).first()
    assert clazz is not None
    return clazz.id


def test_list_history_unauthenticated_returns_401(client: TestClient) -> None:
    """AC-04: Unauthenticated request must return 401 Unauthorized."""
    res = client.get("/api/history")
    assert res.status_code == 401


def test_list_history_initially_empty(client: TestClient, db_session: Session) -> None:
    """AC-04: A new student initially has an empty session list."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    res = client.get("/api/history", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_create_and_list_sessions(client: TestClient, db_session: Session) -> None:
    """AC-03, AC-04, AC-06: Create a session and verify it is returned sorted newest first."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    # 1. Create first session
    create_res1 = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "First Session"},
    )
    assert create_res1.status_code == 201
    s1_id = create_res1.json()["id"]

    # 2. Create second session
    create_res2 = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "Second Session"},
    )
    assert create_res2.status_code == 201
    s2_id = create_res2.json()["id"]

    # In fast in-memory SQLite, both sessions can be created in the same second.
    # Set an earlier updated_at on s1 to guarantee deterministic ordering:
    s1_obj = db_session.get(ChatSession, uuid.UUID(s1_id))
    assert s1_obj is not None
    s1_obj.updated_at = datetime.now(UTC) - timedelta(minutes=5)
    s1_obj.created_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.commit()

    # 3. List sessions: s2 must appear before s1 (updated_at DESC)
    list_res = client.get(f"/api/history?class_id={class_id}", headers=headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) == 2
    assert items[0]["id"] == s2_id
    assert items[1]["id"] == s1_id


def test_append_message_and_retrieve_detail(client: TestClient, db_session: Session) -> None:
    """AC-01, AC-02, AC-05, AC-07: Append messages and load chronological transcript."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    # Create session
    create_res = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "Algorithm Query"},
    )
    session_id = create_res.json()["id"]

    # Append user question
    msg1 = client.post(
        f"/api/history/sessions/{session_id}/messages",
        headers=headers,
        json={"role": "USER", "content": "What is Dijkstra algorithm?", "used_web_search": False},
    )
    assert msg1.status_code == 201

    # Append assistant answer
    msg2 = client.post(
        f"/api/history/sessions/{session_id}/messages",
        headers=headers,
        json={
            "role": "ASSISTANT",
            "content": "Dijkstra is a shortest path algorithm.",
            "used_web_search": True,
        },
    )
    assert msg2.status_code == 201
    assert msg2.json()["used_web_search"] is True

    # Retrieve transcript
    detail_res = client.get(f"/api/history/{session_id}", headers=headers)
    assert detail_res.status_code == 200
    messages = detail_res.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "USER"
    assert messages[0]["content"] == "What is Dijkstra algorithm?"
    assert messages[1]["role"] == "ASSISTANT"
    assert messages[1]["used_web_search"] is True


def test_row_level_security_forbidden(client: TestClient, db_session: Session) -> None:
    """User B cannot view or append messages to User A's session (403 Forbidden)."""
    student_headers = _login(client, "student@academic.edu.vn", "Student@123")
    trainer_headers = _login(client, "teacher@academic.edu.vn", "Teacher@123")
    class_id = str(_get_test_class_id(db_session))

    # Student creates session
    create_res = client.post(
        "/api/history/sessions",
        headers=student_headers,
        json={"class_id": class_id, "title": "Private Discussion"},
    )
    session_id = create_res.json()["id"]

    # Trainer tries to access student's session -> 403 Forbidden
    res = client.get(f"/api/history/{session_id}", headers=trainer_headers)
    assert res.status_code == 403
    assert "not own this chat session" in res.json()["detail"]


def test_non_existent_session_returns_404(client: TestClient) -> None:
    """Querying a non-existent session UUID returns 404 Not Found."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    fake_id = str(uuid.uuid4())
    res = client.get(f"/api/history/{fake_id}", headers=headers)
    assert res.status_code == 404


def test_delete_session_cascades(client: TestClient, db_session: Session) -> None:
    """AC-05: Deleting a session cascades deletion and is no longer retrievable."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    create_res = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "To be deleted"},
    )
    session_id = create_res.json()["id"]

    # Add message
    client.post(
        f"/api/history/sessions/{session_id}/messages",
        headers=headers,
        json={"role": "USER", "content": "Temporary message"},
    )

    # Delete session
    del_res = client.delete(f"/api/history/{session_id}", headers=headers)
    assert del_res.status_code == 200

    # Verify session is gone
    get_res = client.get(f"/api/history/{session_id}", headers=headers)
    assert get_res.status_code == 404


def test_delete_session_does_not_affect_other_sessions(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    """AC-01: Deleting one session leaves other sessions and their messages intact."""
    qdrant = MagicMock()
    monkeypatch.setattr(history_service, "get_qdrant_client", lambda: qdrant)
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    create_1 = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "Session to delete"},
    )
    assert create_1.status_code == 201
    session_1_id = create_1.json()["id"]

    create_2 = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "Session to keep"},
    )
    assert create_2.status_code == 201
    session_2_id = create_2.json()["id"]

    for session_id, label in ((session_1_id, "Session 1"), (session_2_id, "Session 2")):
        for role in ("USER", "ASSISTANT"):
            msg_res = client.post(
                f"/api/history/sessions/{session_id}/messages",
                headers=headers,
                json={"role": role, "content": f"{label} {role.lower()} message"},
            )
            assert msg_res.status_code == 201

    delete_res = client.delete(f"/api/history/{session_1_id}", headers=headers)
    assert delete_res.status_code == 200
    assert qdrant.delete.called

    deleted_detail = client.get(f"/api/history/{session_1_id}", headers=headers)
    assert deleted_detail.status_code == 404

    kept_detail = client.get(f"/api/history/{session_2_id}", headers=headers)
    assert kept_detail.status_code == 200
    kept_messages = kept_detail.json()["messages"]
    assert len(kept_messages) == 2
    assert {message["content"] for message in kept_messages} == {
        "Session 2 user message",
        "Session 2 assistant message",
    }

    list_res = client.get(f"/api/history?class_id={class_id}", headers=headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == session_2_id


def test_delete_session_rejects_another_user(client: TestClient, db_session: Session) -> None:
    """AC-02: A non-owner receives 403 and the session remains intact."""
    student_headers = _login(client, "student@academic.edu.vn", "Student@123")
    trainer_headers = _login(client, "teacher@academic.edu.vn", "Teacher@123")
    class_id = str(_get_test_class_id(db_session))

    create_res = client.post(
        "/api/history/sessions",
        headers=student_headers,
        json={"class_id": class_id, "title": "Owner only"},
    )
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]

    msg_res = client.post(
        f"/api/history/sessions/{session_id}/messages",
        headers=student_headers,
        json={"role": "USER", "content": "Private question"},
    )
    assert msg_res.status_code == 201

    forbidden = client.delete(f"/api/history/{session_id}", headers=trainer_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Access forbidden: you do not own this chat session."

    detail_res = client.get(f"/api/history/{session_id}", headers=student_headers)
    assert detail_res.status_code == 200
    assert len(detail_res.json()["messages"]) == 1

    db_session.expire_all()
    assert db_session.get(ChatSession, uuid.UUID(session_id)) is not None


def test_delete_nonexistent_session_returns_404(client: TestClient) -> None:
    """AC-03: Deleting a random UUID returns 404 Not Found."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    fake_id = uuid.uuid4()

    res = client.delete(f"/api/history/{fake_id}", headers=headers)
    assert res.status_code == 404


def test_delete_session_purges_content_gap_vectors(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-03: Web-search vectors are purged and all messages cascade-delete."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    create_res = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "Qdrant cleanup"},
    )
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]
    session_uuid = uuid.UUID(session_id)

    normal_msg = client.post(
        f"/api/history/sessions/{session_id}/messages",
        headers=headers,
        json={"role": "USER", "content": "Normal question", "used_web_search": False},
    )
    assert normal_msg.status_code == 201

    web_msg = client.post(
        f"/api/history/sessions/{session_id}/messages",
        headers=headers,
        json={
            "role": "ASSISTANT",
            "content": "Answer with web fallback",
            "used_web_search": True,
        },
    )
    assert web_msg.status_code == 201
    assert web_msg.json()["used_web_search"] is True
    web_msg_id = web_msg.json()["id"]

    assert db_session.query(ChatMessage).filter(ChatMessage.session_id == session_uuid).count() == 2

    captured_message_ids: list[str] = []

    def fake_delete_content_gap_queries(
        message_ids: list[str], qdrant_client: object | None = None
    ) -> None:
        captured_message_ids.extend(message_ids)

    monkeypatch.setattr(
        history_service,
        "delete_content_gap_queries",
        fake_delete_content_gap_queries,
    )

    delete_res = client.delete(f"/api/history/{session_id}", headers=headers)
    assert delete_res.status_code == 200
    assert captured_message_ids == [web_msg_id]

    db_session.expire_all()
    assert db_session.get(ChatSession, session_uuid) is None
    remaining_messages = (
        db_session.query(ChatMessage).filter(ChatMessage.session_id == session_uuid).count()
    )
    assert remaining_messages == 0


def test_save_chat_turn_service_auto_creates_session_and_truncates_title(
    db_session: Session,
) -> None:
    """AC-01, AC-02, AC-03: save_chat_turn initializes session with first 50 chars as title."""
    student = db_session.query(User).filter(User.email == "student@academic.edu.vn").first()
    clazz = db_session.query(Class).first()

    long_prompt = (
        "Explain to me the fundamentals of database normalization including 1NF 2NF 3NF and BCNF"
    )
    session, user_msg, assistant_msg = history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=clazz.id,
        user_content=long_prompt,
        assistant_content="Normalization reduces redundancy...",
        session_id=None,
        used_web_search=False,
    )

    assert session is not None
    assert len(session.title) <= 50
    assert user_msg.role == "USER"
    assert assistant_msg.role == "ASSISTANT"
    assert assistant_msg.used_web_search is False


def test_message_citations_survive_history_reload(client: TestClient, db_session: Session) -> None:
    """AI-63 AC-03: reopening an old answer must keep its original citations."""

    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    create_res = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "Cited answer"},
    )
    session_id = create_res.json()["id"]

    citation = {
        "index": 1,
        "kind": "curriculum",
        "title": "syllabus.pdf",
        "url": None,
        "snippet": "The deadline is Friday.",
        "document_id": "doc-1",
        "page": 2,
        "pages": [],
        "page_label": None,
        "section": None,
        "indexes": [1, 3],
        "highlights": ["The deadline is Friday. " + "Preserve the complete source passage. " * 12],
    }
    append_res = client.post(
        f"/api/history/sessions/{session_id}/messages",
        headers=headers,
        json={
            "role": "ASSISTANT",
            "content": "The deadline is Friday [1].",
            "used_web_search": False,
            "citations": [citation],
        },
    )
    assert append_res.status_code == 201

    detail_res = client.get(f"/api/history/{session_id}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["messages"][0]["citations"] == [citation]


def test_message_suggested_questions_survive_history_reload(
    client: TestClient, db_session: Session
) -> None:
    """AI-125: reopening an old answer must keep its suggested follow-up questions."""

    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    create_res = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "Suggested questions answer"},
    )
    session_id = create_res.json()["id"]

    suggestions = [
        "What is gradient descent?",
        "How to prevent overfitting?",
    ]
    append_res = client.post(
        f"/api/history/sessions/{session_id}/messages",
        headers=headers,
        json={
            "role": "ASSISTANT",
            "content": "Deep learning models are trained via gradient descent.",
            "used_web_search": False,
            "citations": [],
            "suggested_questions": suggestions,
        },
    )
    assert append_res.status_code == 201

    detail_res = client.get(f"/api/history/{session_id}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["messages"][0]["suggested_questions"] == suggestions


def test_save_chat_turn_persists_suggested_questions(db_session: Session) -> None:
    """AI-125: save_chat_turn saves suggested_questions into assistant message."""
    student = db_session.query(User).filter(User.email == "student@academic.edu.vn").first()
    clazz = db_session.query(Class).first()

    suggestions = ["How does backprop work?", "Why use ReLU?"]
    _session, _user_msg, assistant_msg = history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=clazz.id,
        user_content="What is neural network?",
        assistant_content="Neural networks are interconnected layers.",
        session_id=None,
        used_web_search=False,
        suggested_questions=suggestions,
    )

    assert assistant_msg.suggested_questions == suggestions


def test_save_chat_turn_persists_thinking_metadata(client: TestClient, db_session: Session) -> None:
    """Thinking time and reasoning trace survive a history reload."""
    student = db_session.query(User).filter(User.email == "student@academic.edu.vn").first()
    clazz = db_session.query(Class).first()
    trace = ["Searching class materials.", "Reading lesson.pdf.", "Synthesizing answer."]

    session, _user_msg, assistant_msg = history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=clazz.id,
        user_content="What is a neural network?",
        assistant_content="A neural network is a stack of layers.",
        session_id=None,
        used_web_search=False,
        thinking_ms=4321,
        trace=trace,
    )

    assert assistant_msg.thinking_ms == 4321
    assert assistant_msg.trace == trace

    headers = _login(client, "student@academic.edu.vn", "Student@123")
    detail_res = client.get(f"/api/history/{session.id}", headers=headers)
    assert detail_res.status_code == 200
    persisted = detail_res.json()["messages"][-1]
    assert persisted["thinking_ms"] == 4321
    assert persisted["trace"] == trace


def test_rename_session_updates_title_without_bumping_activity(
    client: TestClient, db_session: Session
) -> None:
    """An owned session can be renamed; the sidebar activity order is preserved."""

    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    create_res = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "Original title"},
    )
    session_id = create_res.json()["id"]
    before = db_session.get(ChatSession, uuid.UUID(session_id)).updated_at

    rename_res = client.patch(
        f"/api/history/{session_id}",
        headers=headers,
        json={"title": "  My renamed conversation  "},
    )

    assert rename_res.status_code == 200
    assert rename_res.json()["title"] == "My renamed conversation"
    db_session.expire_all()
    refreshed = db_session.get(ChatSession, uuid.UUID(session_id))
    assert refreshed.title == "My renamed conversation"
    assert refreshed.updated_at == before


def test_rename_session_rejects_another_users_session(
    client: TestClient, db_session: Session
) -> None:
    """Row-level security also applies to rename requests."""

    student_headers = _login(client, "student@academic.edu.vn", "Student@123")
    trainer_headers = _login(client, "teacher@academic.edu.vn", "Teacher@123")
    class_id = str(_get_test_class_id(db_session))
    create_res = client.post(
        "/api/history/sessions",
        headers=student_headers,
        json={"class_id": class_id, "title": "Private session"},
    )
    session_id = create_res.json()["id"]

    res = client.patch(
        f"/api/history/{session_id}",
        headers=trainer_headers,
        json={"title": "Hijacked"},
    )

    assert res.status_code == 403


def test_rename_session_rejects_blank_title(client: TestClient, db_session: Session) -> None:
    """A rename must contain at least one non-whitespace character."""

    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    create_res = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": "Keep me"},
    )
    session_id = create_res.json()["id"]

    res = client.patch(
        f"/api/history/{session_id}",
        headers=headers,
        json={"title": "   "},
    )

    assert res.status_code == 422


# ---------------------------------------------------------------------------
# AI-97 — Reopen an Old Conversation & Continue (AC-01, AC-02, AC-03)
# ---------------------------------------------------------------------------


def test_save_chat_turn_creates_new_session_when_session_id_none(
    db_session: Session,
) -> None:
    """AC-03: When session_id is None, save_chat_turn creates a new session and 2 messages."""
    student = db_session.query(User).filter(User.email == "student@academic.edu.vn").first()
    assert student is not None
    class_id = _get_test_class_id(db_session)

    session, user_msg, assistant_msg = history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=class_id,
        user_content="What are the prerequisite units?",
        assistant_content="The prerequisites are Unit 1 and Unit 2.",
        session_id=None,
    )

    assert session is not None
    assert session.user_id == student.id
    assert session.class_id == class_id
    assert session.title.startswith("What are the prerequisite")
    assert user_msg.role == "USER"
    assert user_msg.content == "What are the prerequisite units?"
    assert assistant_msg.role == "ASSISTANT"
    assert assistant_msg.content == "The prerequisites are Unit 1 and Unit 2."

    # Verify messages in DB
    detail = history_service.get_session_messages(db_session, session.id, student.id)
    assert len(detail.messages) == 2
    assert detail.messages[0].id == user_msg.id
    assert detail.messages[1].id == assistant_msg.id


def test_save_chat_turn_continues_existing_session_without_creating_new(
    db_session: Session,
) -> None:
    """AC-01, AC-02: Calling save_chat_turn twice with the same session_id appends messages to 1 session."""
    student = db_session.query(User).filter(User.email == "student@academic.edu.vn").first()
    assert student is not None
    class_id = _get_test_class_id(db_session)

    # First turn (create new session)
    session, _, _ = history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=class_id,
        user_content="First question",
        assistant_content="First answer",
        session_id=None,
    )
    session_id = session.id

    # Second turn (continue existing session)
    continued_session, _, _ = history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=class_id,
        user_content="Second question follow-up",
        assistant_content="Second answer with context",
        session_id=session_id,
    )

    assert continued_session.id == session_id

    # Verify exactly 4 messages in that single session in chronological order
    detail = history_service.get_session_messages(db_session, session_id, student.id)
    assert len(detail.messages) == 4
    assert detail.messages[0].content == "First question"
    assert detail.messages[1].content == "First answer"
    assert detail.messages[2].content == "Second question follow-up"
    assert detail.messages[3].content == "Second answer with context"


def test_save_chat_turn_rejects_another_users_session(
    db_session: Session,
) -> None:
    """AC-03 / Security: Reopening and continuing another user's session raises 403 Forbidden."""
    student = db_session.query(User).filter(User.email == "student@academic.edu.vn").first()
    trainer = db_session.query(User).filter(User.email == "teacher@academic.edu.vn").first()
    assert student is not None and trainer is not None
    class_id = _get_test_class_id(db_session)

    # Student creates session
    student_session, _, _ = history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=class_id,
        user_content="Student private question",
        assistant_content="Student answer",
        session_id=None,
    )

    # Trainer attempts to continue student's session -> must raise 403
    with pytest.raises(Exception) as exc_info:
        history_service.save_chat_turn(
            db=db_session,
            user_id=trainer.id,
            class_id=class_id,
            user_content="Trainer hijacking",
            assistant_content="Trainer answer",
            session_id=student_session.id,
        )
    assert "403" in str(exc_info.value) or "forbidden" in str(exc_info.value).lower()


def test_reopen_session_loads_recent_exchanges_in_order(
    db_session: Session,
) -> None:
    """AC-01: Reopening an old session loads its conversation exchanges chronologically."""
    from app.services import chat_context_service

    student = db_session.query(User).filter(User.email == "student@academic.edu.vn").first()
    assert student is not None
    class_id = _get_test_class_id(db_session)

    session, _, _ = history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=class_id,
        user_content="Explain Dijkstra algorithm",
        assistant_content="Dijkstra finds the shortest path.",
        session_id=None,
    )

    history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=class_id,
        user_content="What is its time complexity?",
        assistant_content="With binary heap, it is O((V+E) log V).",
        session_id=session.id,
    )

    exchanges = chat_context_service.load_recent_exchanges(
        db=db_session,
        session_id=session.id,
        user_id=student.id,
        class_id=class_id,
    )

    assert len(exchanges) == 2
    assert exchanges[0].user == "Explain Dijkstra algorithm"
    assert exchanges[0].assistant == "Dijkstra finds the shortest path."
    assert exchanges[1].user == "What is its time complexity?"
    assert exchanges[1].assistant == "With binary heap, it is O((V+E) log V)."


def test_new_chat_does_not_leak_context_from_old_session(
    db_session: Session,
) -> None:
    """AC-03: Switching to a new chat (session_id=None) starts fresh without old exchanges."""
    from app.services import chat_context_service

    student = db_session.query(User).filter(User.email == "student@academic.edu.vn").first()
    assert student is not None
    class_id = _get_test_class_id(db_session)

    # Old session with exchanges
    old_session, _, _ = history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=class_id,
        user_content="Old session question about python",
        assistant_content="Python is dynamically typed.",
        session_id=None,
    )

    # New session started later
    new_session, _, _ = history_service.save_chat_turn(
        db=db_session,
        user_id=student.id,
        class_id=class_id,
        user_content="Brand new session question about docker",
        assistant_content="Docker packages applications into containers.",
        session_id=None,
    )

    assert new_session.id != old_session.id

    new_exchanges = chat_context_service.load_recent_exchanges(
        db=db_session,
        session_id=new_session.id,
        user_id=student.id,
        class_id=class_id,
    )

    assert len(new_exchanges) == 1
    assert "docker" in new_exchanges[0].user.lower()
    assert "python" not in new_exchanges[0].user.lower()


# --- AI-101: Search Chat History ---


def _create_search_session(
    client: TestClient,
    headers: dict[str, str],
    class_id: str,
    title: str,
) -> str:
    res = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": title},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _append_search_message(
    client: TestClient,
    headers: dict[str, str],
    session_id: str,
    content: str,
) -> None:
    res = client.post(
        f"/api/history/sessions/{session_id}/messages",
        headers=headers,
        json={"role": "USER", "content": content},
    )
    assert res.status_code == 201, res.text


def test_search_by_title_returns_matching_sessions(
    client: TestClient, db_session: Session
) -> None:
    """AC-01: Tìm theo title trả về session, match_in='title'."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    session_id = _create_search_session(client, headers, class_id, "Thuật toán BFS")

    res = client.get("/api/history/search", params={"q": "BFS"}, headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["query"] == "BFS"
    assert data["items"][0]["session_id"] == session_id
    assert data["items"][0]["match_in"] == "title"
    assert "BFS" in data["items"][0]["snippet"]


def test_search_by_message_content_returns_matching_sessions(
    client: TestClient, db_session: Session
) -> None:
    """AC-01, AC-03: Tìm theo message trả về snippet chứa keyword."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    session_id = _create_search_session(client, headers, class_id, "Recursion")
    _append_search_message(client, headers, session_id, "Giải thích về đệ quy")

    res = client.get("/api/history/search", params={"q": "đệ quy"}, headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["session_id"] == session_id
    assert data["items"][0]["match_in"] == "message"
    assert "đệ quy" in data["items"][0]["snippet"]


def test_search_does_not_return_other_users_sessions(
    client: TestClient, db_session: Session
) -> None:
    """AC-02 RLS: User B không thấy session của User A."""
    student_headers = _login(client, "student@academic.edu.vn", "Student@123")
    trainer_headers = _login(client, "teacher@academic.edu.vn", "Teacher@123")
    class_id = str(_get_test_class_id(db_session))
    _create_search_session(client, student_headers, class_id, "secret session")

    res = client.get("/api/history/search", params={"q": "secret"}, headers=trainer_headers)

    assert res.status_code == 200
    assert res.json()["items"] == []
    assert res.json()["total"] == 0


def test_search_with_no_match_returns_empty_list(client: TestClient) -> None:
    """AC-04: q không khớp → items=[], total=0."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    res = client.get(
        "/api/history/search",
        params={"q": "xyzxyzxyznotexist"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["items"] == []
    assert res.json()["total"] == 0


def test_search_is_case_insensitive(client: TestClient, db_session: Session) -> None:
    """AC-01: Tìm 'THUATTOAN' vẫn khớp title 'thuatToan'."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    session_id = _create_search_session(client, headers, class_id, "thuatToan")

    res = client.get("/api/history/search", params={"q": "THUATTOAN"}, headers=headers)

    assert res.status_code == 200
    assert res.json()["items"][0]["session_id"] == session_id


def test_search_with_empty_q_returns_422(client: TestClient) -> None:
    """Validation: q rỗng hoặc toàn khoảng trắng → HTTP 422."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    assert client.get(
        "/api/history/search", params={"q": ""}, headers=headers
    ).status_code == 422
    assert client.get(
        "/api/history/search", params={"q": "   "}, headers=headers
    ).status_code == 422


def test_search_requires_authentication(client: TestClient) -> None:
    """Security: thiếu token → HTTP 401."""
    assert client.get("/api/history/search", params={"q": "BFS"}).status_code == 401


def test_search_respects_class_id_filter(
    client: TestClient, db_session: Session
) -> None:
    """AC-01: class_id lạ không trả về session của class khác."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    _create_search_session(client, headers, class_id, "BFS in class A")

    res = client.get(
        "/api/history/search",
        params={"q": "BFS", "class_id": str(uuid.uuid4())},
        headers=headers,
    )

    assert res.status_code == 200
    assert res.json()["items"] == []


def test_search_pagination_returns_total_and_slices(
    client: TestClient, db_session: Session
) -> None:
    """AC-01: total phản ánh toàn bộ kết quả, items bị giới hạn bởi limit/offset."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    for index in range(3):
        _create_search_session(client, headers, class_id, f"BFS session {index}")

    first_page = client.get(
        "/api/history/search",
        params={"q": "BFS", "limit": 2, "offset": 0},
        headers=headers,
    )
    second_page = client.get(
        "/api/history/search",
        params={"q": "BFS", "limit": 2, "offset": 2},
        headers=headers,
    )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2
    assert second_page.status_code == 200
    assert second_page.json()["total"] == 3
    assert len(second_page.json()["items"]) == 1


def test_search_escapes_like_wildcards(
    client: TestClient, db_session: Session
) -> None:
    """Security/Correctness: q='%' phải match literal '%', không match tất cả."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    percent_id = _create_search_session(client, headers, class_id, "100% done")
    _create_search_session(client, headers, class_id, "BFS overview")

    res = client.get("/api/history/search", params={"q": "%"}, headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["session_id"] == percent_id


def test_search_title_match_takes_priority_over_message(
    client: TestClient, db_session: Session
) -> None:
    """AC-01: session khớp cả title và message → ưu tiên match_in='title'."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))
    session_id = _create_search_session(client, headers, class_id, "BFS overview")
    _append_search_message(client, headers, session_id, "BFS details")

    res = client.get("/api/history/search", params={"q": "BFS"}, headers=headers)

    assert res.status_code == 200
    assert res.json()["items"][0]["session_id"] == session_id
    assert res.json()["items"][0]["match_in"] == "title"


# --- AI-185: Cursor pagination ---


def _create_cursor_session(
    client: TestClient,
    headers: dict[str, str],
    class_id: str,
    title: str,
    db: Session,
    updated_at: datetime | None = None,
    is_pinned: bool = False,
    pinned_at: datetime | None = None,
) -> str:
    """Create a session and optionally control its sort timestamps directly.

    SQLite is fast enough that several sessions may share the same
    ``updated_at`` second; tests that need a deterministic order set the
    timestamp explicitly. ``pinned_at`` is kept in lockstep with ``is_pinned``
    because the cursor section predicate requires both.
    """
    res = client.post(
        "/api/history/sessions",
        headers=headers,
        json={"class_id": class_id, "title": title},
    )
    assert res.status_code == 201, res.text
    session_id = res.json()["id"]
    if updated_at is not None or is_pinned:
        session = db.get(ChatSession, uuid.UUID(session_id))
        assert session is not None
        if updated_at is not None:
            session.updated_at = updated_at
        if is_pinned:
            session.is_pinned = True
            session.pinned_at = pinned_at or updated_at or datetime.now(UTC)
        db.commit()
    return session_id


def _sweep_cursor(
    client: TestClient,
    headers: dict[str, str],
    section: str,
    class_id: str,
    limit: int,
) -> list[str]:
    """Page through every cursor page and return the ordered id list."""
    ids: list[str] = []
    cursor: str | None = None
    while True:
        params = {"section": section, "class_id": class_id, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        res = client.get("/api/history", params=params, headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        ids.extend(item["id"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return ids


def test_cursor_sweep_returns_every_session_once(
    client: TestClient, db_session: Session
) -> None:
    """AC-05: A full cursor sweep returns every session exactly once, in order."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    base = datetime.now(UTC) - timedelta(minutes=30)
    expected: list[str] = []
    for i in range(10):
        sid = _create_cursor_session(
            client,
            headers,
            class_id,
            f"Cursor sweep {i}",
            db_session,
            updated_at=base + timedelta(minutes=i),
        )
        expected.append(sid)

    got = _sweep_cursor(client, headers, "recent", class_id, limit=3)

    # updated_at DESC, id DESC.
    assert got == list(reversed(expected))
    assert len(got) == len(set(got)) == 10


def test_cursor_stable_when_updated_at_ties(
    client: TestClient, db_session: Session
) -> None:
    """AC-04: Equal updated_at values are broken by id so no row is skipped."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    shared = datetime.now(UTC) - timedelta(hours=1)
    ids = [
        _create_cursor_session(
            client, headers, class_id, f"Tie {i}", db_session, updated_at=shared
        )
        for i in range(5)
    ]

    got = _sweep_cursor(client, headers, "recent", class_id, limit=2)

    assert got == sorted(ids, reverse=True)
    assert len(got) == 5


def test_cursor_insert_between_pages_has_no_duplicate_or_gap(
    client: TestClient, db_session: Session
) -> None:
    """AC-06: A session created mid-pagination is not duplicated or skipped."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    base = datetime.now(UTC) - timedelta(minutes=30)
    original: list[str] = []
    for i in range(5):
        original.append(
            _create_cursor_session(
                client, headers, class_id, f"Before {i}", db_session,
                updated_at=base + timedelta(minutes=i),
            )
        )

    res = client.get(
        "/api/history", params={"section": "recent", "class_id": class_id, "limit": 3},
        headers=headers,
    )
    assert res.status_code == 200
    first_page = [item["id"] for item in res.json()["items"]]
    cursor = res.json()["next_cursor"]
    assert cursor is not None
    assert len(first_page) == 3

    # A brand-new session lands on top of the recent list.
    inserted = _create_cursor_session(
        client, headers, class_id, "Inserted mid-pagination", db_session,
        updated_at=base + timedelta(minutes=60),
    )

    other = _login(client, "teacher@academic.edu.vn", "Teacher@123")
    _create_cursor_session(
        client, other, class_id, "Other user", db_session,
        updated_at=base + timedelta(minutes=61),
    )

    res2 = client.get(
        "/api/history",
        params={"section": "recent", "class_id": class_id, "limit": 3, "cursor": cursor},
        headers=headers,
    )
    assert res2.status_code == 200
    second_page = [item["id"] for item in res2.json()["items"]]

    # The new top row is not repeated (keyset resumes strictly after the
    # cursor), and no original row is skipped.
    assert inserted not in first_page
    assert inserted not in second_page
    seen = first_page + second_page
    assert len(seen) == len(set(seen))
    assert set(seen) == set(original)


def test_cursor_next_cursor_is_null_on_last_page(
    client: TestClient, db_session: Session
) -> None:
    """AC-03: The final page carries next_cursor=null, signalling the end."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    for i in range(4):
        _create_cursor_session(
            client, headers, class_id, f"Last page {i}", db_session,
            updated_at=datetime.now(UTC) - timedelta(minutes=30 - i),
        )

    res = client.get(
        "/api/history", params={"section": "recent", "class_id": class_id, "limit": 4},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 4
    assert body["next_cursor"] is None


def test_cursor_rejects_malformed_cursor(client: TestClient) -> None:
    """A tampered or non-cursor value is rejected with 400."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")

    for bad in ("not-a-cursor", "###", "aGVsbG8="):
        res = client.get(
            "/api/history",
            params={"section": "recent", "cursor": bad},
            headers=headers,
        )
        assert res.status_code == 400, f"cursor={bad!r} -> {res.status_code}"


def test_cursor_rejects_cursor_from_other_section(
    client: TestClient, db_session: Session
) -> None:
    """A 'recent' cursor cannot drive the 'pinned' section (and vice versa)."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    sid = _create_cursor_session(
        client, headers, class_id, "Section mismatch", db_session,
        updated_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    _create_cursor_session(
        client, headers, class_id, "Section mismatch 2", db_session,
        updated_at=datetime.now(UTC) - timedelta(minutes=6),
    )

    res = client.get(
        "/api/history", params={"section": "recent", "class_id": class_id, "limit": 1},
        headers=headers,
    )
    assert res.status_code == 200
    recent_cursor = res.json()["next_cursor"]
    assert recent_cursor is not None
    assert res.json()["items"][0]["id"] == sid

    res2 = client.get(
        "/api/history",
        params={"section": "pinned", "class_id": class_id, "cursor": recent_cursor},
        headers=headers,
    )
    assert res2.status_code == 400


def test_cursor_requires_section_when_cursor_present(client: TestClient) -> None:
    """Passing a cursor without section is an API error (400)."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    res = client.get("/api/history", params={"cursor": "abc"}, headers=headers)
    assert res.status_code == 400


def test_cursor_only_returns_current_users_sessions(
    client: TestClient, db_session: Session
) -> None:
    """RLS: Cursor mode never leaks another user's sessions."""
    student_headers = _login(client, "student@academic.edu.vn", "Student@123")
    trainer_headers = _login(client, "teacher@academic.edu.vn", "Teacher@123")
    class_id = str(_get_test_class_id(db_session))

    own = _create_cursor_session(
        client, student_headers, class_id, "Mine", db_session,
        updated_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    _create_cursor_session(
        client, trainer_headers, class_id, "Not mine", db_session,
        updated_at=datetime.now(UTC) - timedelta(minutes=9),
    )

    got = _sweep_cursor(client, student_headers, "recent", class_id, limit=1)

    assert got == [own]


def test_cursor_respects_class_id_filter(
    client: TestClient, db_session: Session
) -> None:
    """Cursor mode honours the same class_id scope as the legacy endpoint."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    second_class = Class(
        trainer_id=db_session.query(User).filter(User.email == "teacher@academic.edu.vn").first().id,
        code="CS201-B",
        name="Class B",
        semester="1",
        academic_year="2026-2027",
    )
    db_session.add(second_class)
    db_session.commit()
    second_class_id = str(second_class.id)

    a = _create_cursor_session(
        client, headers, class_id, "In class A", db_session,
        updated_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    b = _create_cursor_session(
        client, headers, second_class_id, "In class B", db_session,
        updated_at=datetime.now(UTC) - timedelta(minutes=9),
    )

    got_a = _sweep_cursor(client, headers, "recent", class_id, limit=1)
    got_b = _sweep_cursor(client, headers, "recent", second_class_id, limit=1)

    assert got_a == [a]
    assert got_b == [b]


def test_pinned_section_orders_by_pinned_at_ascending(
    client: TestClient, db_session: Session
) -> None:
    """AC-04: The pinned block is FIFO — oldest pin first."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    base = datetime.now(UTC) - timedelta(hours=3)
    newer = _create_cursor_session(
        client, headers, class_id, "Pinned newer", db_session,
        updated_at=base + timedelta(hours=2),
        is_pinned=True, pinned_at=base + timedelta(hours=2),
    )
    older = _create_cursor_session(
        client, headers, class_id, "Pinned older", db_session,
        updated_at=base + timedelta(hours=1),
        is_pinned=True, pinned_at=base + timedelta(hours=1),
    )
    unpinned = _create_cursor_session(
        client, headers, class_id, "Not pinned", db_session,
        updated_at=base + timedelta(hours=3),
    )

    got = _sweep_cursor(client, headers, "pinned", class_id, limit=1)

    assert got == [older, newer]
    assert unpinned not in got


def test_legacy_offset_mode_still_works(
    client: TestClient, db_session: Session
) -> None:
    """AC-02: Without 'section', the legacy offset path stays unchanged."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    base = datetime.now(UTC) - timedelta(minutes=30)
    for i in range(8):
        _create_cursor_session(
            client, headers, class_id, f"Legacy {i}", db_session,
            updated_at=base + timedelta(minutes=i),
        )

    res = client.get(
        "/api/history",
        params={"class_id": class_id, "offset": 2, "limit": 3},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 8
    assert len(body["items"]) == 3
    assert body["next_cursor"] is None


def test_legacy_response_has_null_next_cursor(
    client: TestClient, db_session: Session
) -> None:
    """AC-02: A legacy response never advertises a cursor continuation."""
    headers = _login(client, "student@academic.edu.vn", "Student@123")
    class_id = str(_get_test_class_id(db_session))

    _create_cursor_session(
        client, headers, class_id, "Legacy null", db_session,
        updated_at=datetime.now(UTC) - timedelta(minutes=5),
    )

    res = client.get("/api/history", params={"class_id": class_id}, headers=headers)
    assert res.status_code == 200
    assert res.json()["next_cursor"] is None
