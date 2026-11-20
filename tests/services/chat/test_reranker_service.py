"""Cross Encoder ordering tests without downloading a model checkpoint."""

from __future__ import annotations

import sys
from contextlib import nullcontext
from types import SimpleNamespace

from app.services import reranker_service
from app.services.rag_service import ScoredChunk


class FakeTensor:
    def __init__(self, value):
        self.value = value

    def to(self, device):
        return self

    def squeeze(self, dimension):
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return self.value


def test_rerank_chunks_orders_by_cross_encoder_logit(monkeypatch) -> None:
    chunks = [
        ScoredChunk("general water note", 0.95, {"document_id": "a"}),
        ScoredChunk("water evaporates and condenses", 0.70, {"document_id": "b"}),
    ]
    captured: dict[str, object] = {}

    class FakeTokenizer:
        def __call__(self, pairs, **kwargs):
            captured["pairs"] = pairs
            captured["max_length"] = kwargs["max_length"]
            return {"input_ids": FakeTensor([1, 2])}

    class FakeModel:
        def __call__(self, **kwargs):
            return SimpleNamespace(logits=FakeTensor([0.1, 2.4]))

    class FakeTorch:
        @staticmethod
        def inference_mode():
            return nullcontext()

    monkeypatch.setitem(sys.modules, "torch", FakeTorch)
    monkeypatch.setattr(
        reranker_service,
        "_load_model",
        lambda: (FakeTokenizer(), FakeModel(), "cpu"),
    )

    ranked = reranker_service.rerank_chunks("water cycle stages", chunks)

    assert [chunk.metadata["document_id"] for chunk in ranked] == ["b", "a"]
    assert captured["pairs"][0] == ("water cycle stages", "general water note")
    assert captured["max_length"] == reranker_service.MAX_SEQUENCE_LENGTH


def test_reranker_is_enabled_by_default() -> None:
    """AI-162: the measured default keeps the Cross Encoder on."""

    from app.config import Settings

    assert Settings(_env_file=None).reranker_enabled is True


def test_disabled_reranker_keeps_vector_order_without_loading_the_model(monkeypatch) -> None:
    """AI-162 AC-04: RERANKER_ENABLED=false skips the Cross Encoder entirely."""

    chunks = [
        ScoredChunk("first by cosine", 0.95, {"document_id": "a"}),
        ScoredChunk("second by cosine", 0.70, {"document_id": "b"}),
    ]

    def fail_load():
        raise AssertionError("Cross Encoder must not load when the reranker is off")

    monkeypatch.setattr(reranker_service.settings, "reranker_enabled", False)
    monkeypatch.setattr(reranker_service, "_load_model", fail_load)

    ranked = reranker_service.rerank_all("water cycle stages", chunks)

    assert [chunk.metadata["document_id"] for chunk in ranked] == ["a", "b"]
    assert [chunk.score for chunk in ranked] == [0.95, 0.70]


def test_disabled_reranker_skips_warm_up(monkeypatch) -> None:
    """A deployment with the reranker off must not pay the model load at startup."""

    loaded = False

    def fake_load():
        nonlocal loaded
        loaded = True
        return (None, None, "cpu")

    monkeypatch.setattr(reranker_service.settings, "reranker_enabled", False)
    monkeypatch.setattr(reranker_service, "_load_model", fake_load)
    monkeypatch.delitem(sys.modules, "pytest", raising=False)

    reranker_service.warm_up()

    assert loaded is False
