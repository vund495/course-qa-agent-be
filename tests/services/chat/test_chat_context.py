"""Conversation memory and follow-up resolution (AI-63)."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401 - register all tables
from app.core.database import Base
from app.models.chat import ChatMessage, ChatSession, ChatWebConsent
from app.services import chat_context_service


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _session(
    db: Session,
    *,
    user_id: uuid.UUID | None = None,
    class_id: uuid.UUID | None = None,
) -> ChatSession:
    session = ChatSession(
        user_id=user_id or uuid.uuid4(),
        class_id=class_id or uuid.uuid4(),
        title="Context test",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _add_exchange(
    db: Session,
    session: ChatSession,
    *,
    question: str,
    answer: str,
    offset: int,
    excluded_from_context: bool = False,
) -> None:
    created = datetime.now(UTC) + timedelta(seconds=offset)
    db.add_all(
        [
            ChatMessage(
                session_id=session.id,
                role="USER",
                content=question,
                created_at=created,
                excluded_from_context=excluded_from_context,
            ),
            ChatMessage(
                session_id=session.id,
                role="ASSISTANT",
                content=answer,
                created_at=created + timedelta(milliseconds=1),
                excluded_from_context=excluded_from_context,
            ),
        ]
    )
    db.commit()


def _add_consent(
    db: Session,
    session: ChatSession,
    *,
    course: ChatMessage | None,
    web: ChatMessage,
    status: str = "consumed",
) -> None:
    now = datetime.now(UTC)
    db.add(
        ChatWebConsent(
            user_id=session.user_id,
            class_id=session.class_id,
            session_id=session.id,
            assistant_message_id=course.id if course is not None else None,
            web_message_id=web.id,
            scope_kind="missing",
            question="question",
            query_text="question",
            scope_segments=["question"],
            status=status,
            expires_at=now + timedelta(minutes=30),
            consumed_at=now if status == "consumed" else None,
        )
    )
    db.commit()


def test_load_recent_exchanges_returns_last_complete_pairs(db_session: Session) -> None:
    session = _session(db_session)
    for index in range(1, 5):
        _add_exchange(
            db_session,
            session,
            question=f"question {index}",
            answer=f"answer {index}",
            offset=index,
        )

    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
        max_exchanges=2,
    )

    assert [exchange.user for exchange in history] == ["question 3", "question 4"]
    assert [exchange.assistant for exchange in history] == ["answer 3", "answer 4"]


def test_default_context_window_keeps_latest_twenty_exchanges(db_session, monkeypatch):
    session = _session(db_session)
    for index in range(1, 23):
        _add_exchange(
            db_session,
            session,
            question=f"question {index}",
            answer=f"answer {index}",
            offset=index,
        )

    monkeypatch.setattr(chat_context_service.settings, "chat_context_exchanges", 20)
    monkeypatch.setattr(chat_context_service.settings, "chat_context_max_chars", 30000)
    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
    )

    assert len(history) == 20
    assert [exchange.user for exchange in history] == [f"question {i}" for i in range(3, 23)]


def test_load_recent_exchanges_drops_orphaned_messages(db_session: Session) -> None:
    session = _session(db_session)
    db_session.add(
        ChatMessage(
            session_id=session.id,
            role="ASSISTANT",
            content="orphaned answer",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    _add_exchange(
        db_session,
        session,
        question="question 1",
        answer="answer 1",
        offset=1,
    )

    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
    )

    assert len(history) == 1
    assert history[0].user == "question 1"


def test_load_recent_exchanges_skips_turns_excluded_from_context(
    db_session: Session,
) -> None:
    session = _session(db_session)
    _add_exchange(
        db_session,
        session,
        question="What is the assignment policy?",
        answer="The policy is in the syllabus.",
        offset=1,
    )
    _add_exchange(
        db_session,
        session,
        question="What are today's lottery numbers?",
        answer="This question appears to be outside the scope of this class.",
        offset=2,
        excluded_from_context=True,
    )

    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
    )

    assert [exchange.user for exchange in history] == ["What is the assignment policy?"]


def test_load_recent_exchanges_enforces_ownership_and_class_scope(
    db_session: Session,
) -> None:
    session = _session(db_session)

    with pytest.raises(HTTPException) as forbidden:
        chat_context_service.load_recent_exchanges(
            db_session,
            session_id=session.id,
            user_id=uuid.uuid4(),
            class_id=session.class_id,
        )
    assert forbidden.value.status_code == 403

    with pytest.raises(HTTPException) as missing:
        chat_context_service.load_recent_exchanges(
            db_session,
            session_id=uuid.uuid4(),
            user_id=session.user_id,
            class_id=session.class_id,
        )
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as wrong_class:
        chat_context_service.load_recent_exchanges(
            db_session,
            session_id=session.id,
            user_id=session.user_id,
            class_id=uuid.uuid4(),
        )
    assert wrong_class.value.status_code == 404


def test_load_recent_exchanges_respects_character_budget(db_session: Session) -> None:
    session = _session(db_session)
    _add_exchange(
        db_session,
        session,
        question="old question " * 10,
        answer="old answer " * 10,
        offset=1,
    )
    _add_exchange(
        db_session,
        session,
        question="new question",
        answer="new answer",
        offset=2,
    )

    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
        max_chars=50,
    )

    assert [exchange.user for exchange in history] == ["new question"]


def test_history_context_drops_old_citation_markers() -> None:
    rendered = chat_context_service.format_history_context(
        [
            chat_context_service.ConversationExchange(
                user="What is the deadline?",
                assistant="The deadline is Friday [1][2].",
            )
        ]
    )

    assert "Friday" in rendered
    assert "[1]" not in rendered
    assert "[2]" not in rendered


def test_condense_question_uses_recent_history() -> None:
    captured: list[object] = []

    class FakeModel:
        async def ainvoke(self, messages):
            captured.extend(messages)
            return SimpleNamespace(content="When is the database assignment deadline?")

    history = [
        chat_context_service.ConversationExchange(
            user="What is the database assignment policy?",
            assistant="The policy describes the assignment deadline.",
        )
    ]

    rewritten = asyncio.run(
        chat_context_service.condense_question(
            history,
            "So when is the deadline?",
            model=FakeModel(),
        )
    )

    assert rewritten == "When is the database assignment deadline?"
    rendered = "\n".join(str(message.content) for message in captured)
    assert "database assignment policy" in rendered
    assert "So when is the deadline?" in rendered


def test_condense_question_falls_back_to_the_original_question() -> None:
    class BrokenModel:
        async def ainvoke(self, messages):
            raise RuntimeError("provider unavailable")

    history = [
        chat_context_service.ConversationExchange(
            user="What is the deadline?",
            assistant="Friday.",
        )
    ]

    rewritten = asyncio.run(
        chat_context_service.condense_question(
            history,
            "What about that one?",
            model=BrokenModel(),
        )
    )

    assert rewritten == "What about that one?"


def test_condense_question_falls_back_to_the_class_subject() -> None:
    class BrokenModel:
        async def ainvoke(self, messages):
            raise RuntimeError("provider unavailable")

    history = [
        chat_context_service.ConversationExchange(
            user="What is a pointer?",
            assistant="A pointer stores a memory address.",
        )
    ]

    rewritten = asyncio.run(
        chat_context_service.condense_question(
            history,
            "Cho t ví dụ đi",
            model=BrokenModel(),
            class_name="C++ - Toturial",
            class_description="Con trỏ, OOP và STL.",
        )
    )

    assert rewritten == "Cho t ví dụ đi (C++ - Toturial — Con trỏ, OOP và STL)"


def test_condense_question_qualifies_an_empty_rewrite_with_the_class() -> None:
    class EmptyModel:
        async def ainvoke(self, messages):
            return SimpleNamespace(content="   ")

    history = [
        chat_context_service.ConversationExchange(
            user="What is a pointer?",
            assistant="A pointer stores a memory address.",
        )
    ]

    rewritten = asyncio.run(
        chat_context_service.condense_question(
            history,
            "Cho t ví dụ đi",
            model=EmptyModel(),
            class_name="C++ - Toturial",
            class_description="Con trỏ, OOP và STL.",
        )
    )

    assert rewritten == "Cho t ví dụ đi (C++ - Toturial — Con trỏ, OOP và STL)"


def test_condense_question_does_not_repeat_a_class_already_in_the_question() -> None:
    class BrokenModel:
        async def ainvoke(self, messages):
            raise RuntimeError("provider unavailable")

    history = [
        chat_context_service.ConversationExchange(
            user="What is a pointer?",
            assistant="A pointer stores a memory address.",
        )
    ]

    rewritten = asyncio.run(
        chat_context_service.condense_question(
            history,
            "C++ có con trỏ không?",
            model=BrokenModel(),
            class_name="C++",
            class_description="Con trỏ, OOP và STL.",
        )
    )

    assert rewritten == "C++ có con trỏ không?"


def test_condense_question_stops_at_the_shared_deadline(monkeypatch) -> None:
    async def hanging_gateway(*args, **kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(chat_context_service.gateway, "ainvoke_chat", hanging_gateway)
    history = [
        chat_context_service.ConversationExchange(
            user="What is a pointer?",
            assistant="A pointer stores a memory address.",
        )
    ]

    async def run() -> tuple[str, float]:
        started = time.monotonic()
        deadline = asyncio.get_running_loop().time() + 0.1
        rewritten = await chat_context_service.condense_question(
            history,
            "Cho t ví dụ đi",
            class_name="C++ - Toturial",
            class_description="Con trỏ, OOP và STL.",
            deadline=deadline,
        )
        return rewritten, time.monotonic() - started

    rewritten, elapsed = asyncio.run(run())

    assert rewritten == chat_context_service.qualify_with_class(
        "Cho t ví dụ đi",
        "C++ - Toturial",
        "Con trỏ, OOP và STL.",
    )
    # The shared deadline must not be extended by a fresh fallback timeout.
    assert elapsed < 1


def test_load_recent_exchanges_prefers_consumed_web_answer_for_same_turn(
    db_session: Session,
) -> None:
    session = _session(db_session)
    now = datetime.now(UTC)
    user = ChatMessage(
        session_id=session.id,
        role="USER",
        content="Who discovered photosynthesis?",
        created_at=now,
    )
    db_session.add(user)
    db_session.flush()
    course = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="Partial course answer.",
        parent_message_id=user.id,
        created_at=now + timedelta(milliseconds=1),
    )
    db_session.add(course)
    db_session.flush()
    web = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="Full web answer.",
        used_web_search=True,
        parent_message_id=course.id,
        created_at=now + timedelta(seconds=1),
    )
    db_session.add(web)
    db_session.flush()
    db_session.add(
        ChatWebConsent(
            user_id=session.user_id,
            class_id=session.class_id,
            session_id=session.id,
            assistant_message_id=course.id,
            web_message_id=web.id,
            scope_kind="missing",
            question="Who discovered photosynthesis?",
            query_text="Who discovered photosynthesis?",
            scope_segments=["Who discovered photosynthesis?"],
            status="consumed",
            expires_at=now + timedelta(minutes=30),
            consumed_at=now + timedelta(seconds=1),
        )
    )
    db_session.commit()

    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
    )

    assert len(history) == 1
    assert history[0].user == "Who discovered photosynthesis?"
    assert history[0].assistant == "Full web answer."


def test_load_recent_exchanges_keeps_consumed_web_with_its_own_same_session_turn(
    db_session: Session,
) -> None:
    session = _session(db_session)
    now = datetime.now(UTC)
    first_user = ChatMessage(
        session_id=session.id,
        role="USER",
        content="first question",
        created_at=now,
    )
    db_session.add(first_user)
    db_session.flush()
    first_course = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="first course answer",
        parent_message_id=first_user.id,
        created_at=now + timedelta(milliseconds=1),
    )
    db_session.add(first_course)
    db_session.flush()
    second_user = ChatMessage(
        session_id=session.id,
        role="USER",
        content="second question",
        created_at=now + timedelta(seconds=1),
    )
    db_session.add(second_user)
    db_session.flush()
    second_course = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="second course answer",
        parent_message_id=second_user.id,
        created_at=now + timedelta(seconds=1, milliseconds=1),
    )
    db_session.add(second_course)
    db_session.flush()
    first_web = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="first web answer",
        used_web_search=True,
        parent_message_id=first_course.id,
        created_at=now + timedelta(seconds=2),
    )
    db_session.add(first_web)
    db_session.flush()
    _add_consent(db_session, session, course=first_course, web=first_web)

    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
    )

    assert [exchange.user for exchange in history] == [
        "first question",
        "second question",
    ]
    assert [exchange.assistant for exchange in history] == [
        "first web answer",
        "second course answer",
    ]


def test_load_recent_exchanges_ignores_unconsumed_web_answers(db_session: Session) -> None:
    session = _session(db_session)
    now = datetime.now(UTC)
    user = ChatMessage(
        session_id=session.id,
        role="USER",
        content="question",
        created_at=now,
    )
    db_session.add(user)
    db_session.flush()
    course = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="course answer",
        parent_message_id=user.id,
        created_at=now + timedelta(milliseconds=1),
    )
    db_session.add(course)
    db_session.flush()
    web = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="unconsumed web answer",
        used_web_search=True,
        parent_message_id=course.id,
        created_at=now + timedelta(seconds=1),
    )
    db_session.add(web)
    db_session.flush()
    _add_consent(db_session, session, course=course, web=web, status="processing")

    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
    )

    assert len(history) == 1
    assert history[0].assistant == "course answer"


def test_load_recent_exchanges_ignores_orphan_assistant_parent(db_session: Session) -> None:
    session = _session(db_session)
    now = datetime.now(UTC)
    user = ChatMessage(
        session_id=session.id,
        role="USER",
        content="question",
        created_at=now,
    )
    db_session.add(user)
    db_session.flush()
    orphan = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="orphan answer",
        parent_message_id=uuid.uuid4(),
        created_at=now + timedelta(milliseconds=1),
    )
    db_session.add(orphan)
    db_session.commit()

    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
    )

    assert history == []


def test_load_recent_exchanges_ignores_unconsumed_direct_user_web(db_session: Session) -> None:
    session = _session(db_session)
    now = datetime.now(UTC)
    user = ChatMessage(
        session_id=session.id,
        role="USER",
        content="question",
        created_at=now,
    )
    db_session.add(user)
    db_session.flush()
    web = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="unconsumed direct web",
        used_web_search=True,
        parent_message_id=user.id,
        created_at=now + timedelta(seconds=1),
    )
    db_session.add(web)
    db_session.flush()
    _add_consent(db_session, session, course=None, web=web, status="processing")

    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
    )

    assert history == []


def test_load_recent_exchanges_keeps_interleaved_direct_user_parent_legacy_web(
    db_session: Session,
) -> None:
    session = _session(db_session)
    now = datetime.now(UTC)
    first_user = ChatMessage(
        session_id=session.id,
        role="USER",
        content="legacy A",
        created_at=now,
    )
    db_session.add(first_user)
    db_session.flush()
    second_user = ChatMessage(
        session_id=session.id,
        role="USER",
        content="question B",
        created_at=now + timedelta(seconds=1),
    )
    db_session.add(second_user)
    db_session.flush()
    second_course = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="course B",
        parent_message_id=second_user.id,
        created_at=now + timedelta(seconds=1, milliseconds=1),
    )
    db_session.add(second_course)
    db_session.flush()
    legacy_web_a = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content="legacy web A",
        used_web_search=True,
        parent_message_id=first_user.id,
        created_at=now + timedelta(seconds=2),
    )
    db_session.add(legacy_web_a)
    db_session.commit()

    history = chat_context_service.load_recent_exchanges(
        db_session,
        session_id=session.id,
        user_id=session.user_id,
        class_id=session.class_id,
    )

    assert [exchange.user for exchange in history] == ["legacy A", "question B"]
    assert [exchange.assistant for exchange in history] == [
        "legacy web A",
        "course B",
    ]
