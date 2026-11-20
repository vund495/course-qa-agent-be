"""AI-161 — the retrieval evaluation harness stays runnable and honest.

These tests never call Gemini, Qdrant, or the Cross Encoder: they cover the
fixed question set, the metric arithmetic, the offline embedder, and a small
end-to-end run of the harness with the hashing embedder.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval" / "retrieval"
QUESTIONS_PATH = EVAL_DIR / "questions.json"
CORPUS_DIR = EVAL_DIR / "corpus"


def _load_harness():
    spec = importlib.util.spec_from_file_location("ai161_run_eval", EVAL_DIR / "run_eval.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def harness():
    return _load_harness()


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))


def test_question_set_has_twenty_to_thirty_real_questions(payload):
    """AC-01: a fixed set of 20-30 questions lives in the repo."""

    questions = payload["questions"]
    assert 20 <= len(questions) <= 30
    assert len({item["id"] for item in questions}) == len(questions)
    assert all(item["question"].strip() for item in questions)


def test_every_expected_document_exists_in_the_corpus(payload):
    """An expectation pointing at a missing file would silently score zero."""

    corpus_files = {path.name for path in CORPUS_DIR.glob("*.md")}
    assert corpus_files
    for item in payload["questions"]:
        assert item["expected_documents"], item["id"]
        assert set(item["expected_documents"]) <= corpus_files, item["id"]


def test_out_of_scope_probes_are_present(payload):
    """The false "not found" metric needs off-topic probes to stay honest."""

    assert len(payload["out_of_scope"]) >= 3


def test_hashing_embedder_is_deterministic_and_normalised(harness):
    embedder = harness.HashingEmbedder()
    first = embedder.embed_query("How do I declare a list?")
    second = embedder.embed_query("How do I declare a list?")
    assert first == second
    assert len(first) == embedder.dimension
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_metrics_hit_rate_mrr_and_false_not_found(harness):
    """AC-02: the harness reports hit-rate, MRR, and the false not-found rate."""

    def chunk(file_name: str, score: float):
        return harness.RankedChunk(
            document_id=file_name, file_name=file_name, score=score, content=""
        )

    outcomes = [
        # Rank 1 hit, answered.
        harness.QuestionOutcome(
            "q1", "a", ("a.md",), [chunk("a.md", 0.9), chunk("b.md", 0.5)], 0.9, 0.45
        ),
        # Rank 2 hit, answered.
        harness.QuestionOutcome(
            "q2", "b", ("b.md",), [chunk("a.md", 0.9), chunk("b.md", 0.8)], 0.9, 0.45
        ),
        # Miss, and the router would refuse: a false "not found".
        harness.QuestionOutcome("q3", "c", ("c.md",), [chunk("a.md", 0.2)], 0.2, 0.45),
        # Miss, but still answered from the wrong document.
        harness.QuestionOutcome("q4", "d", ("d.md",), [chunk("a.md", 0.7)], 0.7, 0.45),
    ]
    result = harness.ConfigurationResult(
        chunk_size=800, threshold=0.45, top_k=3, chunk_count=10, outcomes=outcomes
    )

    assert result.hit_rate == pytest.approx(0.5)
    assert result.mrr == pytest.approx((1.0 + 0.5 + 0.0 + 0.0) / 4)
    assert result.false_not_found_rate == pytest.approx(0.25)


def test_hit_at_k_respects_the_cutoff(harness):
    ranked = [
        harness.RankedChunk(document_id="x", file_name="x.md", score=0.9, content=""),
        harness.RankedChunk(document_id="y", file_name="y.md", score=0.8, content=""),
    ]
    outcome = harness.QuestionOutcome("q", "q", ("y.md",), ranked, 0.9, 0.45)
    assert outcome.hit_at(1) is False
    assert outcome.hit_at(2) is True
    assert outcome.reciprocal_rank() == pytest.approx(0.5)


def test_threshold_changes_the_false_not_found_rate(harness):
    ranked = [harness.RankedChunk(document_id="a", file_name="a.md", score=0.5, content="")]
    strict = harness.QuestionOutcome("q", "q", ("a.md",), ranked, 0.5, 0.6)
    lenient = harness.QuestionOutcome("q", "q", ("a.md",), ranked, 0.5, 0.4)
    assert strict.false_not_found() is True
    assert lenient.false_not_found() is False


def test_chunk_corpus_uses_the_production_chunkers(harness):
    documents = harness.load_corpus(CORPUS_DIR)
    small = harness.chunk_corpus(documents, 600)
    large = harness.chunk_corpus(documents, 1000)
    assert small and large
    # Smaller chunks can only produce more pieces, never fewer.
    assert len(small) >= len(large)
    assert all(chunk.metadata["class_id"] == harness.CLASS_ID for chunk in small)
    assert all(chunk.metadata["embedding_text"] for chunk in small)


def test_latency_percentiles_use_nearest_rank(harness):
    """AI-162 AC-02: p50 and p95 are reported from the per-question latencies."""

    def outcome(latency_ms: float):
        return harness.QuestionOutcome("q", "q", ("a.md",), [], None, 0.45, latency_ms=latency_ms)

    result = harness.ConfigurationResult(
        chunk_size=800,
        threshold=0.45,
        top_k=3,
        chunk_count=10,
        outcomes=[outcome(value) for value in (10.0, 20.0, 30.0, 40.0, 100.0)],
    )

    assert result.latency_percentile(50) == pytest.approx(30.0)
    assert result.latency_percentile(95) == pytest.approx(100.0)
    assert result.as_dict()["p50_latency_ms"] == pytest.approx(30.0)
    assert result.as_dict()["p95_latency_ms"] == pytest.approx(100.0)


def test_rerank_comparison_pairs_on_and_off(harness):
    """AI-162 AC-01/AC-02: on and off are compared for the same configuration."""

    def result(rerank: bool, ranked: list, p50: float):
        return harness.ConfigurationResult(
            chunk_size=800,
            threshold=0.45,
            top_k=3,
            chunk_count=10,
            rerank=rerank,
            outcomes=[
                harness.QuestionOutcome(
                    "q", "q", ("a.md",), ranked, ranked[0].score, 0.45, latency_ms=p50
                )
            ],
            out_of_scope=[("x", 0.0, False)],
        )

    hit_first = [harness.RankedChunk("a", "a.md", 0.9, "")]
    hit_second = [
        harness.RankedChunk("b", "b.md", 0.9, ""),
        harness.RankedChunk("a", "a.md", 0.8, ""),
    ]
    comparison = harness.rerank_comparison(
        [result(True, hit_first, 1118.5), result(False, hit_second, 430.3)]
    )

    assert len(comparison["pairs"]) == 1
    pair = comparison["pairs"][0]
    assert pair["mrr_on"] == pytest.approx(1.0)
    assert pair["mrr_off"] == pytest.approx(0.5)
    assert pair["p50_ms_on"] == pytest.approx(1118.5)
    assert pair["p50_ms_off"] == pytest.approx(430.3)


def test_rerank_comparison_skips_unpaired_configurations(harness):
    """A configuration measured in only one mode has no delta to report."""

    only_on = harness.ConfigurationResult(
        chunk_size=800, threshold=0.45, top_k=3, chunk_count=10, rerank=True
    )
    assert harness.rerank_comparison([only_on])["pairs"] == []


def test_end_to_end_run_reports_every_metric(harness, tmp_path, capsys):
    """One command produces a report with all three metrics for every config."""

    report_path = tmp_path / "report.md"
    exit_code = harness.main(
        [
            "--embedding",
            "hashing",
            "--chunk-sizes",
            "600",
            "800",
            "--thresholds",
            "0.3",
            "0.6",
            "--top-ks",
            "3",
            "--report",
            str(report_path),
            "--json",
            str(tmp_path / "report.json"),
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    report = report_path.read_text(encoding="utf-8")
    assert "hit-rate" in report
    assert "MRR" in report
    assert "false not-found" in report

    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert data["embedder"] == "hashing-1536"
    assert len(data["results"]) == 4  # 2 chunk sizes x 2 thresholds x 1 top_k
    for row in data["results"]:
        assert 0.0 <= row["hit_rate"] <= 1.0
        assert 0.0 <= row["mrr"] <= 1.0
        assert 0.0 <= row["false_not_found_rate"] <= 1.0
        assert row["rerank"] is True
        assert row["p50_latency_ms"] >= 0.0
        assert row["p95_latency_ms"] >= row["p50_latency_ms"]


def test_end_to_end_run_compares_reranker_on_and_off(harness, tmp_path, capsys):
    """AI-162 AC-01: one command measures both modes and pairs them."""

    report_path = tmp_path / "report.md"
    exit_code = harness.main(
        [
            "--embedding",
            "hashing",
            "--rerank",
            "both",
            "--chunk-sizes",
            "800",
            "--thresholds",
            "0.45",
            "--top-ks",
            "3",
            "--report",
            str(report_path),
            "--json",
            str(tmp_path / "report.json"),
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    report = report_path.read_text(encoding="utf-8")
    assert "Reranker on vs off" in report

    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert [row["rerank"] for row in data["results"]] == [True, False]
    pairs = data["rerank_comparison"]["pairs"]
    assert len(pairs) == 1
    assert pairs[0]["p50_ms_on"] >= 0.0
    assert pairs[0]["p95_ms_on"] >= pairs[0]["p50_ms_on"]
