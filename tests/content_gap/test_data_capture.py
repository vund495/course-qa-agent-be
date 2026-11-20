"""Phase 1 unit tests for Content Gap query embedding capture and logging (AI-91, AC-01 to AC-03).

Covers:
- Vector store collection creation for 'content_gap_queries'
- Query embedding sync to Qdrant without question text (privacy compliance)
- Correct payload fields (class_id, student_id, timestamp, source, fallback_reason, concept_tag, embedding_model_version)
- Point deletion by message ID on session cleanup
- QdrantStore.similarity_search_by_vector_with_score
"""

import asyncio
import threading
import uuid
from unittest.mock import MagicMock

from qdrant_client.http import models as qmodels

from app.services import content_gap_telemetry, history_service
from app.services.vector_store.qdrant_store import QdrantStore


def test_ensure_content_gap_collection_creates_when_missing():
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = False

    history_service.ensure_content_gap_collection(mock_client)

    mock_client.collection_exists.assert_called_once_with(
        history_service.CONTENT_GAP_COLLECTION
    )
    mock_client.create_collection.assert_called_once()
    _, kwargs = mock_client.create_collection.call_args
    assert kwargs["collection_name"] == history_service.CONTENT_GAP_COLLECTION
    vectors_config = kwargs["vectors_config"]
    assert vectors_config.size == 1536
    assert vectors_config.distance == qmodels.Distance.COSINE


def test_ensure_content_gap_collection_skips_when_exists():
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True

    history_service.ensure_content_gap_collection(mock_client)

    mock_client.collection_exists.assert_called_once_with(
        history_service.CONTENT_GAP_COLLECTION
    )
    mock_client.create_collection.assert_not_called()


def test_sync_content_gap_query_stores_vector_without_question_text():
    mock_client = MagicMock()
    dummy_vector = [0.1] * 1536
    msg_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    student_id = str(uuid.uuid4())

    history_service.sync_content_gap_query(
        message_id=msg_id,
        class_id=class_id,
        student_id=student_id,
        embedding=dummy_vector,
        source="web",
        fallback_reason="similarity_below_threshold",
        concept_tag="binary search",
        embedding_model_version="text-embedding-004",
        qdrant_client=mock_client,
    )

    mock_client.upsert.assert_called_once()
    call_kwargs = mock_client.upsert.call_args.kwargs
    assert call_kwargs["collection_name"] == history_service.CONTENT_GAP_COLLECTION
    points = call_kwargs["points"]
    assert len(points) == 1

    point = points[0]
    assert point.id == msg_id
    assert point.vector == dummy_vector

    payload = point.payload
    # AC-01: payload must contain the required fields
    assert payload["class_id"] == class_id
    assert payload["student_id"] == student_id
    assert payload["source"] == "web"
    assert payload["fallback_reason"] == "similarity_below_threshold"
    assert payload["concept_tag"] == "binary search"
    assert payload["embedding_model_version"] == "text-embedding-004"
    assert "timestamp" in payload

    # Strict Privacy Check: AC-01 prohibits storing question / query text
    assert "question" not in payload
    assert "query" not in payload
    assert "prompt" not in payload
    assert "text" not in payload
    assert "content" not in payload


def test_sync_content_gap_query_handles_empty_embedding_gracefully():
    mock_client = MagicMock()
    # None or empty embedding should not call upsert
    history_service.sync_content_gap_query(
        message_id=str(uuid.uuid4()),
        class_id=str(uuid.uuid4()),
        student_id=str(uuid.uuid4()),
        embedding=[],
        qdrant_client=mock_client,
    )
    mock_client.upsert.assert_not_called()


def test_sync_content_gap_query_exception_does_not_raise():
    mock_client = MagicMock()
    mock_client.upsert.side_effect = RuntimeError("Qdrant unreachable")

    # Should log warning but not raise error to break user chat turn
    history_service.sync_content_gap_query(
        message_id=str(uuid.uuid4()),
        class_id=str(uuid.uuid4()),
        student_id=str(uuid.uuid4()),
        embedding=[0.2] * 1536,
        source="material",
        qdrant_client=mock_client,
    )


def test_delete_content_gap_queries():
    mock_client = MagicMock()
    message_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

    history_service.delete_content_gap_queries(
        message_ids=message_ids,
        qdrant_client=mock_client,
    )

    mock_client.delete.assert_called_once()
    call_kwargs = mock_client.delete.call_args.kwargs
    assert call_kwargs["collection_name"] == history_service.CONTENT_GAP_COLLECTION
    points_selector = call_kwargs["points_selector"]
    assert points_selector.points == message_ids


def test_qdrant_store_similarity_search_by_vector_with_score():
    mock_vector_store = MagicMock(spec=["similarity_search_with_score_by_vector"])
    mock_doc = MagicMock()
    mock_doc.page_content = "Introduction to Algorithms"
    mock_doc.metadata = {"document_id": "doc-1", "page": 1}
    mock_vector_store.similarity_search_with_score_by_vector.return_value = [
        (mock_doc, 0.88)
    ]

    store = object.__new__(QdrantStore)
    store.vector_store = mock_vector_store

    vector = [0.05] * 1536
    results = store.similarity_search_by_vector_with_score(
        embedding=vector,
        k=3,
        class_id="class-xyz",
    )

    assert len(results) == 1
    doc, score = results[0]
    assert score == 0.88
    assert doc.page_content == "Introduction to Algorithms"
    assert doc.metadata["document_id"] == "doc-1"

    mock_vector_store.similarity_search_with_score_by_vector.assert_called_once()
    _, kwargs = mock_vector_store.similarity_search_with_score_by_vector.call_args
    assert kwargs["k"] == 3
    qfilter = kwargs["filter"]
    assert qfilter is not None
    assert qfilter.must[0].key == "metadata.class_id"
    assert qfilter.must[0].match.value == "class-xyz"


def test_material_capture_does_not_overwrite_consumed_web_source():
    mock_client = MagicMock()
    msg_id = str(uuid.uuid4())
    history_service.sync_content_gap_query(
        message_id=msg_id,
        class_id=str(uuid.uuid4()),
        student_id=str(uuid.uuid4()),
        embedding=[0.1] * 1536,
        source="material",
        concept_tag="",
        qdrant_client=mock_client,
        web_consumed=lambda: True,
    )

    point = mock_client.upsert.call_args.kwargs["points"][0]
    assert point.payload["source"] == "web"
    assert point.payload["concept_tag"] == ""


class _FakeQdrant:
    def __init__(self):
        self.points: dict[str, object] = {}
        self.payloads: list[dict] = []

    def collection_exists(self, _name):
        return True

    def create_collection(self, **_kwargs):
        return None

    def upsert(self, collection_name=None, points=None, **kwargs):
        for point in points:
            self.points[str(point.id)] = point

    def delete(self, collection_name=None, points_selector=None, **kwargs):
        for point_id in points_selector.points:
            self.points.pop(str(point_id), None)

    def set_payload(self, collection_name=None, payload=None, points=None, **kwargs):
        self.payloads.append({"payload": payload, "points": points})
        for point_id in points:
            point = self.points.get(str(point_id))
            if point is not None:
                point.payload.update(payload)


def test_delete_waits_for_running_upsert_and_removes_the_late_point():
    msg_id = str(uuid.uuid4())
    upsert_started = threading.Event()
    release_upsert = threading.Event()
    client = _FakeQdrant()

    def blocking_upsert(collection_name=None, points=None, **kwargs):
        upsert_started.set()
        assert release_upsert.wait(timeout=2.0)
        for point in points:
            client.points[str(point.id)] = point

    client.upsert = blocking_upsert  # type: ignore[method-assign]

    async def scenario():
        assert content_gap_telemetry.schedule_capture(
            history_service.sync_content_gap_query,
            message_id=msg_id,
            class_id=str(uuid.uuid4()),
            student_id=str(uuid.uuid4()),
            embedding=[0.1] * 4,
            source="material",
            qdrant_client=client,
        )
        for _ in range(200):
            if upsert_started.is_set():
                break
            await asyncio.sleep(0.01)
        assert upsert_started.is_set()

        delete_finished = threading.Event()

        def run_delete():
            history_service.delete_content_gap_queries([msg_id], qdrant_client=client)
            delete_finished.set()

        delete_thread = threading.Thread(target=run_delete)
        delete_thread.start()
        await asyncio.sleep(0.05)
        assert delete_finished.is_set() is False

        release_upsert.set()
        await asyncio.to_thread(delete_thread.join, 2.0)
        await content_gap_telemetry.wait_for_tasks(timeout=2.0)

        assert delete_thread.is_alive() is False

    asyncio.run(scenario())

    assert msg_id not in client.points
    assert content_gap_telemetry.active_state_count() == 0
    assert content_gap_telemetry.schedule_capture(
        history_service.sync_content_gap_query,
        message_id=msg_id,
        class_id=str(uuid.uuid4()),
        student_id=str(uuid.uuid4()),
        embedding=[0.1] * 4,
        source="material",
        qdrant_client=client,
    ) is False
    assert msg_id not in client.points


def test_telemetry_state_is_removed_after_the_worker_finishes():
    client = _FakeQdrant()
    msg_id = str(uuid.uuid4())

    async def scenario():
        assert content_gap_telemetry.schedule_capture(
            history_service.sync_content_gap_query,
            message_id=msg_id,
            class_id=str(uuid.uuid4()),
            student_id=str(uuid.uuid4()),
            embedding=[0.1] * 4,
            source="material",
            qdrant_client=client,
        )
        await content_gap_telemetry.wait_for_tasks(timeout=2.0)

    asyncio.run(scenario())

    assert msg_id in client.points
    assert content_gap_telemetry.active_state_count() == 0


def test_web_update_keeps_the_same_point_and_final_source_web():
    client = _FakeQdrant()
    msg_id = str(uuid.uuid4())
    upsert_started = threading.Event()
    release_upsert = threading.Event()
    update_calls: list[tuple[str, str]] = []

    def blocking_upsert(collection_name=None, points=None, **kwargs):
        upsert_started.set()
        assert release_upsert.wait(timeout=2.0)
        for point in points:
            client.points[str(point.id)] = point

    client.upsert = blocking_upsert  # type: ignore[method-assign]

    def update_with_fake_client(message_id, source="web", **_kwargs):
        update_calls.append((str(message_id), source))
        history_service.update_content_gap_source(
            message_id,
            source=source,
            qdrant_client=client,
        )

    async def scenario():
        assert content_gap_telemetry.schedule_capture(
            history_service.sync_content_gap_query,
            message_id=msg_id,
            class_id=str(uuid.uuid4()),
            student_id=str(uuid.uuid4()),
            embedding=[0.1] * 4,
            source="material",
            qdrant_client=client,
        )
        for _ in range(200):
            if upsert_started.is_set():
                break
            await asyncio.sleep(0.01)
        assert upsert_started.is_set()
        assert content_gap_telemetry.schedule_web_update(
            update_with_fake_client,
            message_id=msg_id,
        )
        release_upsert.set()
        await content_gap_telemetry.wait_for_tasks(timeout=2.0)

    asyncio.run(scenario())

    assert update_calls == [(msg_id, "web")]
    assert list(client.points) == [msg_id]
    assert client.points[msg_id].payload["source"] == "web"
    assert any(
        entry["points"] == [msg_id] and entry["payload"].get("source") == "web"
        for entry in client.payloads
    )
    assert content_gap_telemetry.active_state_count() == 0


def test_deleted_tombstones_are_bounded(monkeypatch):
    monkeypatch.setattr(content_gap_telemetry, "MAX_DELETED_TOMBSTONES", 2)
    client = MagicMock()
    for _ in range(3):
        history_service.delete_content_gap_queries(
            [str(uuid.uuid4())],
            qdrant_client=client,
        )

    assert content_gap_telemetry.deleted_tombstone_count() <= 2
