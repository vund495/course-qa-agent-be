"""Content Gap grouping by turn/parent and consumed web consent (regression)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.category import ClassCategory
from app.models.chat import ChatMessage, ChatSession, ChatWebConsent
from app.models.course import Class, Enrollment
from app.models.user import Role, User
from app.services import content_gap_service, history_service

NO_EVIDENCE = (
    "I could not find enough evidence in this class's materials to answer that. "
    "You can accept a web search."
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    trainer_role = Role(name="TRAINER")
    student_role = Role(name="STUDENT")
    session.add_all([trainer_role, student_role])
    session.flush()
    trainer = User(role_id=trainer_role.id, email="t@test.vn", full_name="Trainer")
    session.add(trainer)
    session.flush()
    clazz = Class(
        trainer_id=trainer.id,
        code="CS-GAP",
        name="Content Gap",
        semester="1",
        academic_year="2026-2027",
    )
    session.add(clazz)
    session.flush()
    students = []
    for index in range(3):
        student = User(
            role_id=student_role.id,
            email=f"gap{index}@test.vn",
            full_name=f"Gap {index}",
        )
        session.add(student)
        session.flush()
        session.add(
            Enrollment(class_id=clazz.id, student_id=student.id, status="ACTIVE")
        )
        students.append(student)
    category = ClassCategory(class_id=clazz.id, name="Pointers")
    session.add(category)
    session.commit()
    session.info.update(
        class_id=clazz.id,
        category_id=category.id,
        students=[student.id for student in students],
    )
    yield session
    session.close()


def _session(db, student_id) -> ChatSession:
    chat = ChatSession(
        user_id=student_id,
        class_id=db.info["class_id"],
        title="Gap",
    )
    db.add(chat)
    db.flush()
    return chat


def _message(
    db,
    chat,
    role,
    content,
    at,
    *,
    parent=None,
    web=False,
    excluded=False,
):
    message = ChatMessage(
        session_id=chat.id,
        role=role,
        content=content,
        used_web_search=web,
        parent_message_id=parent.id if parent else None,
        excluded_from_context=excluded,
        created_at=at,
    )
    db.add(message)
    db.flush()
    return message


def _consent(db, chat, user_id, course, web, status="consumed", *, assistant_id=None):
    at = datetime.now(UTC)
    consent = ChatWebConsent(
        user_id=user_id,
        class_id=db.info["class_id"],
        session_id=chat.id,
        assistant_message_id=(
            assistant_id if assistant_id is not None else (course.id if course else None)
        ),
        web_message_id=web.id if web else None,
        scope_kind="full",
        question=course.content if course else "question",
        query_text="question",
        scope_segments=["question"],
        status=status,
        expires_at=at + timedelta(minutes=30),
        consumed_at=at if status == "consumed" else None,
    )
    db.add(consent)
    db.commit()
    return consent


def _dashboard(db):
    return content_gap_service.compute_content_gap_dashboard(
        db, db.info["class_id"], force_refresh=True
    )


def _topic(db, response):
    return next(
        topic
        for topic in response.topics
        if topic.category_id == str(db.info["category_id"])
    )


def test_full_answer_counts_material_once(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Pointers question?", now)
    _message(db, chat, "ASSISTANT", "Material answer", now, parent=user)
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.material_answers == 1
    assert topic.web_fallbacks == 0
    assert topic.dedup_web_fallbacks == 0


def test_no_evidence_then_consumed_web_counts_web_only(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Pointers question?", now)
    course = _message(
        db, chat, "ASSISTANT", NO_EVIDENCE, now, parent=user, excluded=True
    )
    web = _message(
        db, chat, "ASSISTANT", "Web answer", now, parent=course, web=True
    )
    _consent(db, chat, db.info["students"][0], course, web)
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.material_answers == 0
    assert topic.web_fallbacks == 1
    assert topic.dedup_web_fallbacks == 1


def test_material_course_with_consumed_web_counts_web_not_material(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Pointers question?", now)
    course = _message(
        db, chat, "ASSISTANT", "Partial material", now, parent=user
    )
    web = _message(
        db, chat, "ASSISTANT", "Web answer", now, parent=course, web=True
    )
    _consent(db, chat, db.info["students"][0], course, web)
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.material_answers == 0
    assert topic.web_fallbacks == 1


@pytest.mark.parametrize("status", ["pending", "declined", "expired", "processing"])
def test_unconsumed_consent_never_increases_web_count(db, status):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Pointers question?", now)
    course = _message(
        db, chat, "ASSISTANT", "Material answer", now, parent=user
    )
    web = _message(
        db, chat, "ASSISTANT", "Web answer", now, parent=course, web=True
    )
    _consent(db, chat, db.info["students"][0], course, web, status=status)
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 0
    assert topic.dedup_web_fallbacks == 0
    assert topic.material_answers == 1


def test_duplicate_consumed_consents_count_the_turn_once(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Pointers question?", now)
    course = _message(
        db, chat, "ASSISTANT", NO_EVIDENCE, now, parent=user, excluded=True
    )
    web = _message(
        db, chat, "ASSISTANT", "Web answer", now, parent=course, web=True
    )
    _consent(db, chat, db.info["students"][0], course, web)
    _consent(db, chat, db.info["students"][0], course, web)
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 1
    assert topic.dedup_web_fallbacks == 1


def test_interleaved_turns_attach_web_to_the_right_question(db):
    first = _session(db, db.info["students"][0])
    second = _session(db, db.info["students"][1])
    now = datetime.now(UTC)
    user_a = _message(db, first, "USER", "Pointers A?", now)
    course_a = _message(
        db, first, "ASSISTANT", NO_EVIDENCE, now, parent=user_a, excluded=True
    )
    user_b = _message(db, second, "USER", "Pointers B?", now + timedelta(minutes=1))
    _message(
        db, second, "ASSISTANT", "Material B", now + timedelta(minutes=1), parent=user_b
    )
    web_a = _message(
        db,
        first,
        "ASSISTANT",
        "Web A",
        now + timedelta(minutes=2),
        parent=course_a,
        web=True,
    )
    _consent(db, first, db.info["students"][0], course_a, web_a)
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 1
    assert topic.material_answers == 1
    web_question = topic.reason_groups[0].questions[0].question
    assert web_question == "Pointers A?"


def test_legacy_direct_web_and_adjacent_material_are_kept(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    _message(db, chat, "USER", "Legacy web pointers?", now)
    _message(
        db, chat, "ASSISTANT", "Legacy web answer", now + timedelta(seconds=1), web=True
    )
    later = now + timedelta(minutes=5)
    _message(db, chat, "USER", "Legacy material pointers?", later)
    _message(
        db,
        chat,
        "ASSISTANT",
        "Legacy material answer",
        later + timedelta(seconds=1),
    )
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 1
    assert topic.material_answers == 1


def test_save_chat_turn_creates_one_material_point_keyed_by_assistant_id(db, monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        history_service,
        "sync_content_gap_query",
        lambda **kwargs: calls.append(kwargs),
    )
    chat = _session(db, db.info["students"][0])

    _session_record, _user, assistant = history_service.save_chat_turn(
        db,
        user_id=db.info["students"][0],
        class_id=db.info["class_id"],
        user_content="Pointers question?",
        assistant_content="Course answer",
        session_id=chat.id,
        query_embedding=[0.1, 0.2, 0.3],
        fallback_reason="insufficient_context",
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["message_id"] == str(assistant.id)
    assert call["source"] == "material"
    assert call["fallback_reason"] == "insufficient_context"
    assert call["embedding"] == [0.1, 0.2, 0.3]
    assert "question" not in call
    assert "query_text" not in call


def test_consumed_web_offer_updates_the_same_point_not_a_second_vector(monkeypatch):
    client = MagicMock()
    history_service.update_content_gap_source(
        "assistant-message-1",
        source="web",
        qdrant_client=client,
    )

    client.set_payload.assert_called_once_with(
        collection_name=history_service.CONTENT_GAP_COLLECTION,
        payload={"source": "web"},
        points=["assistant-message-1"],
    )
    client.upsert.assert_not_called()


def test_delete_session_cleans_points_for_material_none_and_web_assistants(db, monkeypatch):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Pointers question?", now)
    course = _message(
        db, chat, "ASSISTANT", NO_EVIDENCE, now + timedelta(seconds=1), parent=user, excluded=True
    )
    web = _message(
        db,
        chat,
        "ASSISTANT",
        "Web answer",
        now + timedelta(seconds=2),
        parent=course,
        web=True,
    )
    db.commit()

    deleted: list[str] = []
    monkeypatch.setattr(
        history_service,
        "delete_content_gap_queries",
        lambda message_ids, qdrant_client=None: deleted.extend(message_ids),
    )

    history_service.delete_session(db, chat.id, db.info["students"][0])

    assert set(deleted) == {str(course.id), str(web.id)}
    assert str(user.id) not in deleted


def test_failed_web_attempt_keeps_the_course_answer_as_material(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Pointers question?", now)
    course = _message(
        db, chat, "ASSISTANT", "Partial material", now, parent=user
    )
    _consent(db, chat, db.info["students"][0], course, None, status="pending")
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.material_answers == 1
    assert topic.web_fallbacks == 0
    assert topic.dedup_web_fallbacks == 0


def test_same_session_interleaved_turns_keep_web_with_its_own_question(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    first_user = _message(db, chat, "USER", "Pointers A?", now)
    first_course = _message(
        db, chat, "ASSISTANT", "Material A", now + timedelta(milliseconds=1), parent=first_user
    )
    second_user = _message(db, chat, "USER", "Pointers B?", now + timedelta(seconds=1))
    _message(
        db,
        chat,
        "ASSISTANT",
        "Material B",
        now + timedelta(seconds=1, milliseconds=1),
        parent=second_user,
    )
    first_web = _message(
        db,
        chat,
        "ASSISTANT",
        "Web A",
        now + timedelta(seconds=2),
        parent=first_course,
        web=True,
    )
    _consent(db, chat, db.info["students"][0], first_course, first_web)
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 1
    assert topic.material_answers == 1
    assert topic.reason_groups[0].questions[0].question == "Pointers A?"


def test_consumed_consent_for_another_course_does_not_upgrade_the_turn(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Pointers question?", now)
    course = _message(db, chat, "ASSISTANT", "Material answer", now, parent=user)
    web = _message(
        db, chat, "ASSISTANT", "Web answer", now + timedelta(seconds=1), parent=course, web=True
    )
    _consent(
        db,
        chat,
        db.info["students"][0],
        course,
        web,
        assistant_id=uuid.uuid4(),
    )
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 0
    assert topic.material_answers == 1


def test_direct_user_parent_web_with_processing_consent_is_not_legacy(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Pointers question?", now)
    web = _message(
        db, chat, "ASSISTANT", "Unconsumed web", now + timedelta(seconds=1), parent=user, web=True
    )
    _consent(db, chat, db.info["students"][0], None, web, status="processing")
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 0
    assert topic.material_answers == 0


def test_legacy_direct_user_parent_web_without_consent_is_kept(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Legacy pointers?", now)
    _message(
        db,
        chat,
        "ASSISTANT",
        "Legacy web answer",
        now + timedelta(seconds=1),
        parent=user,
        web=True,
    )
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 1
    assert topic.material_answers == 0


def test_web_child_without_consent_does_not_upgrade_the_course_turn(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    user = _message(db, chat, "USER", "Pointers question?", now)
    course = _message(db, chat, "ASSISTANT", "Material answer", now, parent=user)
    _message(
        db,
        chat,
        "ASSISTANT",
        "Unconsented web",
        now + timedelta(seconds=1),
        parent=course,
        web=True,
    )
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 0
    assert topic.material_answers == 1


def test_orphan_web_answer_is_not_counted(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    _message(db, chat, "USER", "Pointers question?", now)
    _message(
        db,
        chat,
        "ASSISTANT",
        "Orphan web",
        now + timedelta(seconds=1),
        parent=SimpleNamespace(id=uuid.uuid4()),
        web=True,
    )
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 0
    assert topic.material_answers == 0


def test_interleaved_direct_user_parent_legacy_web_is_kept(db):
    chat = _session(db, db.info["students"][0])
    now = datetime.now(UTC)
    first_user = _message(db, chat, "USER", "Legacy pointers A?", now)
    second_user = _message(db, chat, "USER", "Pointers B?", now + timedelta(seconds=1))
    _message(
        db,
        chat,
        "ASSISTANT",
        "Material B",
        now + timedelta(seconds=1, milliseconds=1),
        parent=second_user,
    )
    _message(
        db,
        chat,
        "ASSISTANT",
        "Legacy web A",
        now + timedelta(seconds=2),
        parent=first_user,
        web=True,
    )
    db.commit()

    topic = _topic(db, _dashboard(db))

    assert topic.web_fallbacks == 1
    assert topic.material_answers == 1
    assert topic.reason_groups[0].questions[0].question == "Legacy pointers A?"
