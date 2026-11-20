"""AI-161 — measured retrieval evaluation harness.

Runs the production retrieval path (``markdown_chunker`` -> ``recursive_chunker``
-> ``QdrantStore`` -> ``rag_service.retrieve_class_chunks`` -> Cross Encoder
rerank -> threshold routing) over a fixed question set and reports hit-rate,
MRR, and the false "not found" rate for every chunk size / threshold / top-k
combination.

One command, from the backend root::

    uv run python eval/retrieval/run_eval.py

The default embedder is ``gemini`` (the production ``gemini-embedding-2`` model,
which needs ``GEMINI_API_KEY``). ``--embedding hashing`` swaps in a deterministic
offline embedder so the harness also runs without credentials or network; the
report records which embedder produced the numbers.

Nothing here touches Postgres or a running Qdrant: the corpus is chunked in
memory and indexed into an embedded Qdrant collection, and the AI-39
"retrievable document" guard is replaced by the corpus manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

from langchain_core.embeddings import Embeddings

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_QUESTIONS = EVAL_DIR / "questions.json"
DEFAULT_CORPUS = EVAL_DIR / "corpus"
DEFAULT_REPORT = EVAL_DIR / "results" / "latest.md"

# The production chat path reranks RERANK_CANDIDATES (15) chunks and keeps
# RERANK_TOP_K (6); the benchmark sweeps the candidate pool instead.
DEFAULT_CHUNK_SIZES = (600, 800, 1000)
DEFAULT_THRESHOLDS = (0.30, 0.45, 0.60)
DEFAULT_TOP_KS = (3, 5, 10)
DEFAULT_CANDIDATES = 15
DEFAULT_RERANK_TOP_K = 6
# A question that the reranker scores below this is treated as "not found" by
# the harness, mirroring the production lower threshold default (0.45).
FALSE_NOT_FOUND_THRESHOLD = 0.45

CLASS_ID = "00000000-0000-4000-8000-000000000161"
COLLECTION_NAME = "ai161-retrieval-eval"


# --- Embedders -------------------------------------------------------------


class HashingEmbedder(Embeddings):
    """Deterministic offline embedder: hashed unigrams + bigrams, L2 normalised.

    It is a lexical proxy for a semantic model, not a replacement. It exists so
    the harness is reproducible in CI and on machines without an API key; the
    report always names the embedder that produced its numbers.
    """

    name = "hashing-1536"

    def __init__(self, dimension: int = 1536) -> None:
        self.dimension = dimension

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        features = tokens + [f"{a}_{b}" for a, b in pairwise(tokens)]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            vector[int.from_bytes(digest, "big") % self.dimension] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def build_embedder(kind: str):
    """Return the embedder named on the command line."""

    if kind == "hashing":
        return HashingEmbedder()
    if kind == "gemini":
        from app.services.embedding.gemini_embedding import GeminiEmbedding

        return GeminiEmbedding()
    raise ValueError(f"Unknown embedder {kind!r}; use 'gemini' or 'hashing'.")


# --- Corpus and index ------------------------------------------------------


@dataclass(frozen=True)
class CorpusDocument:
    """One source file of the evaluation corpus."""

    document_id: str
    file_name: str
    markdown: str


def load_corpus(corpus_dir: Path) -> list[CorpusDocument]:
    """Read every Markdown file of the corpus, sorted for a stable order."""

    documents = []
    for path in sorted(corpus_dir.glob("*.md")):
        documents.append(
            CorpusDocument(
                document_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"ai161:{path.name}")),
                file_name=path.name,
                markdown=path.read_text(encoding="utf-8"),
            )
        )
    if not documents:
        raise SystemExit(f"No Markdown files found in {corpus_dir}.")
    return documents


def chunk_corpus(documents: Sequence[CorpusDocument], chunk_size: int) -> list[Any]:
    """Chunk the corpus exactly like ``ingestion_service.process_document``."""

    from app.services.ingestion.chunker import (
        build_chunk_context,
        markdown_chunker,
        recursive_chunker,
    )

    chunks = []
    for document in documents:
        metadata = {
            "document_id": document.document_id,
            "class_id": CLASS_ID,
            "file_name": document.file_name,
            "file_type": "md",
        }
        pieces = recursive_chunker(
            markdown_chunker(document.markdown, metadata=metadata),
            chunk_size=chunk_size,
        )
        for index, piece in enumerate(pieces):
            piece.metadata["chunk_index"] = index
            piece.metadata["embedding_text"] = build_chunk_context(
                piece.page_content, piece.metadata
            )
        chunks.extend(pieces)
    return chunks


def build_store(chunks: list[Any], embedder, *, in_memory: bool):
    """Index chunks through the production ``QdrantStore``.

    ``in_memory`` swaps the Qdrant client for the embedded one so the harness
    needs no server; the store, payload shape, and search code stay production.
    """

    from qdrant_client import QdrantClient

    from app.services.vector_store import qdrant_store
    from app.services.vector_store.qdrant_store import QdrantStore

    original_client = qdrant_store.QdrantClient
    if in_memory:
        qdrant_store.QdrantClient = lambda *args, **kwargs: QdrantClient(":memory:")
    try:
        store = QdrantStore(
            embeddings=embedder,
            collection_name=COLLECTION_NAME,
            vector_size=embedder.dimension if hasattr(embedder, "dimension") else 1536,
        )
        store.add_documents(
            chunks,
            embedding_texts=[chunk.metadata["embedding_text"] for chunk in chunks],
        )
    finally:
        qdrant_store.QdrantClient = original_client
    return store


# --- Retrieval -------------------------------------------------------------


@dataclass
class RankedChunk:
    """One reranked chunk with the document it came from."""

    document_id: str
    file_name: str
    score: float
    content: str


def retrieve(
    store,
    embedder,
    question: str,
    *,
    candidates: int,
    rerank_top_k: int,
    rerank: bool = True,
) -> list[RankedChunk]:
    """Run the production retrieval + rerank path for one question.

    ``rerank=False`` mirrors ``RERANKER_ENABLED=false``: the Cross Encoder is
    skipped and the vector-store order and cosine scores are kept (AI-162).
    """

    from app.services import rag_service
    from app.services.reranker_service import rerank_all

    query_vector = embedder.embed_query(question)
    pairs = store.similarity_search_by_vector_with_score(
        query_vector, k=candidates, class_id=CLASS_ID
    )
    scored = [
        rag_service.ScoredChunk(
            content=document.page_content,
            score=float(score),
            metadata=dict(document.metadata or {}),
        )
        for document, score in pairs
    ]
    scored.sort(key=lambda chunk: chunk.score, reverse=True)
    if not scored:
        return []
    ranked = rerank_all(question, scored) if rerank else scored
    return [
        RankedChunk(
            document_id=str(chunk.metadata.get("document_id", "")),
            file_name=str(chunk.metadata.get("file_name", "")),
            score=float(chunk.score),
            content=chunk.content,
        )
        for chunk in ranked[:rerank_top_k]
    ]


# --- Metrics ---------------------------------------------------------------


@dataclass
class QuestionOutcome:
    """Per-question measurement for one configuration."""

    question_id: str
    question: str
    expected: tuple[str, ...]
    ranked: list[RankedChunk]
    top_score: float | None
    threshold: float
    latency_ms: float = 0.0

    @property
    def first_relevant_rank(self) -> int | None:
        for rank, chunk in enumerate(self.ranked, start=1):
            if chunk.file_name in self.expected:
                return rank
        return None

    def hit_at(self, k: int) -> bool:
        rank = self.first_relevant_rank
        return rank is not None and rank <= k

    def reciprocal_rank(self) -> float:
        rank = self.first_relevant_rank
        return 1.0 / rank if rank else 0.0

    def answered(self) -> bool:
        """True when the router would answer from the curriculum."""

        return self.top_score is not None and self.top_score >= self.threshold

    def false_not_found(self) -> bool:
        """An in-scope question the router refuses to answer from documents."""

        return not self.answered()


@dataclass
class ConfigurationResult:
    """Aggregate metrics for one (chunk_size, threshold, top_k) configuration."""

    chunk_size: int
    threshold: float
    top_k: int
    chunk_count: int
    rerank: bool = True
    outcomes: list[QuestionOutcome] = field(default_factory=list)
    out_of_scope: list[tuple[str, float | None, bool]] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(o.hit_at(self.top_k) for o in self.outcomes) / len(self.outcomes)

    @property
    def mrr(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(o.reciprocal_rank() for o in self.outcomes) / len(self.outcomes)

    @property
    def false_not_found_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(o.false_not_found() for o in self.outcomes) / len(self.outcomes)

    @property
    def out_of_scope_rejection_rate(self) -> float:
        if not self.out_of_scope:
            return 0.0
        return sum(not answered for _, _, answered in self.out_of_scope) / len(self.out_of_scope)

    @property
    def mean_top_score(self) -> float:
        scores = [o.top_score for o in self.outcomes if o.top_score is not None]
        return sum(scores) / len(scores) if scores else 0.0

    @property
    def latencies_ms(self) -> list[float]:
        return [o.latency_ms for o in self.outcomes]

    def latency_percentile(self, percentile: float) -> float:
        """Nearest-rank latency percentile, in milliseconds."""

        values = sorted(self.latencies_ms)
        if not values:
            return 0.0
        rank = max(1, math.ceil(percentile / 100.0 * len(values)))
        return values[rank - 1]

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_size": self.chunk_size,
            "threshold": self.threshold,
            "top_k": self.top_k,
            "chunk_count": self.chunk_count,
            "rerank": self.rerank,
            "hit_rate": round(self.hit_rate, 4),
            "mrr": round(self.mrr, 4),
            "false_not_found_rate": round(self.false_not_found_rate, 4),
            "out_of_scope_rejection_rate": round(self.out_of_scope_rejection_rate, 4),
            "mean_top_score": round(self.mean_top_score, 4),
            "p50_latency_ms": round(self.latency_percentile(50), 2),
            "p95_latency_ms": round(self.latency_percentile(95), 2),
        }


def evaluate_configuration(
    *,
    chunk_size: int,
    threshold: float,
    top_k: int,
    questions: Sequence[dict[str, Any]],
    out_of_scope: Sequence[dict[str, Any]],
    retrieve_fn,
    chunk_count: int,
    rerank: bool = True,
) -> ConfigurationResult:
    """Score one configuration against the fixed question set."""

    result = ConfigurationResult(
        chunk_size=chunk_size,
        threshold=threshold,
        top_k=top_k,
        chunk_count=chunk_count,
        rerank=rerank,
    )
    for item in questions:
        ranked, latency_ms = retrieve_fn(item["question"])
        top_score = ranked[0].score if ranked else None
        result.outcomes.append(
            QuestionOutcome(
                question_id=item["id"],
                question=item["question"],
                expected=tuple(item["expected_documents"]),
                ranked=ranked,
                top_score=top_score,
                threshold=threshold,
                latency_ms=latency_ms,
            )
        )
    for item in out_of_scope:
        ranked, _ = retrieve_fn(item["question"])
        top_score = ranked[0].score if ranked else None
        result.out_of_scope.append(
            (item["id"], top_score, top_score is not None and top_score >= threshold)
        )
    return result


# --- Reporting -------------------------------------------------------------


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def rerank_comparison(results: Sequence[ConfigurationResult]) -> dict[str, Any]:
    """AI-162: pair each configuration with its reranker-off counterpart.

    Only configurations that were measured in both modes are compared, so the
    delta is never computed against a different chunk size or threshold.
    """

    by_key = {(r.chunk_size, round(r.threshold, 4), r.top_k, r.rerank): r for r in results}
    pairs = []
    for (chunk_size, threshold, top_k, rerank), on in by_key.items():
        if not rerank:
            continue
        off = by_key.get((chunk_size, threshold, top_k, False))
        if off is None:
            continue
        pairs.append(
            {
                "chunk_size": chunk_size,
                "threshold": threshold,
                "top_k": top_k,
                "hit_rate_on": round(on.hit_rate, 4),
                "hit_rate_off": round(off.hit_rate, 4),
                "mrr_on": round(on.mrr, 4),
                "mrr_off": round(off.mrr, 4),
                "false_not_found_on": round(on.false_not_found_rate, 4),
                "false_not_found_off": round(off.false_not_found_rate, 4),
                "out_of_scope_rejection_on": round(on.out_of_scope_rejection_rate, 4),
                "out_of_scope_rejection_off": round(off.out_of_scope_rejection_rate, 4),
                "p50_ms_on": round(on.latency_percentile(50), 2),
                "p50_ms_off": round(off.latency_percentile(50), 2),
                "p95_ms_on": round(on.latency_percentile(95), 2),
                "p95_ms_off": round(off.latency_percentile(95), 2),
            }
        )
    return {"pairs": pairs}


def render_report(
    *,
    embedder_name: str,
    question_count: int,
    out_of_scope_count: int,
    results: Sequence[ConfigurationResult],
    best: ConfigurationResult,
    elapsed_seconds: float,
) -> str:
    """Render the Markdown report committed under ``eval/retrieval/results``."""

    lines = [
        "# AI-161 — Retrieval parameter benchmark",
        "",
        "Generated by `eval/retrieval/run_eval.py`; do not edit by hand.",
        "",
        f"- Embedder: `{embedder_name}`",
        f"- In-scope questions: {question_count}",
        f"- Out-of-scope probes: {out_of_scope_count}",
        f"- Configurations: {len(results)}",
        f"- Wall clock: {elapsed_seconds:.1f}s",
        "",
        "## Metrics",
        "",
        "- **Hit-rate** — share of questions whose expected document appears in the top-k.",
        "- **MRR** — mean reciprocal rank of the first expected document.",
        (
            '- **False "not found" rate** — share of in-scope questions whose best reranked '
            "score falls below the threshold, so the router would refuse to answer from documents."
        ),
        "- **Out-of-scope rejection** — share of off-topic probes correctly refused.",
        "- **p50 / p95 latency** — per-question retrieval latency in milliseconds.",
        "",
        "## Results",
        "",
        "| chunk_size | threshold | top_k | rerank | chunks | hit-rate | MRR | false not-found | out-of-scope rejection | mean top score | p50 ms | p95 ms |",
        "| ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        lines.append(
            f"| {result.chunk_size} | {result.threshold:.2f} | {result.top_k} | "
            f"{'on' if result.rerank else 'off'} | {result.chunk_count} | "
            f"{_pct(result.hit_rate)} | {result.mrr:.3f} | "
            f"{_pct(result.false_not_found_rate)} | {_pct(result.out_of_scope_rejection_rate)} | "
            f"{result.mean_top_score:.3f} | {result.latency_percentile(50):.1f} | "
            f"{result.latency_percentile(95):.1f} |"
        )

    pairs = rerank_comparison(results)["pairs"]
    if pairs:
        lines += [
            "",
            "## Reranker on vs off (AI-162)",
            "",
            "Same chunk size, threshold and top-k; only the Cross Encoder differs.",
            "",
            "| chunk_size | threshold | top_k | hit-rate on / off | MRR on / off | false not-found on / off | out-of-scope rejection on / off | p50 ms on / off | p95 ms on / off |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for pair in pairs:
            lines.append(
                f"| {pair['chunk_size']} | {pair['threshold']:.2f} | {pair['top_k']} | "
                f"{_pct(pair['hit_rate_on'])} / {_pct(pair['hit_rate_off'])} | "
                f"{pair['mrr_on']:.3f} / {pair['mrr_off']:.3f} | "
                f"{_pct(pair['false_not_found_on'])} / {_pct(pair['false_not_found_off'])} | "
                f"{_pct(pair['out_of_scope_rejection_on'])} / "
                f"{_pct(pair['out_of_scope_rejection_off'])} | "
                f"{pair['p50_ms_on']:.1f} / {pair['p50_ms_off']:.1f} | "
                f"{pair['p95_ms_on']:.1f} / {pair['p95_ms_off']:.1f} |"
            )

    lines += [
        "",
        "## Per-question detail (best configuration)",
        "",
        f"chunk_size={best.chunk_size}, threshold={best.threshold:.2f}, top_k={best.top_k}",
        "",
        "| id | expected | first expected rank | top score | answered | question |",
        "| --- | --- | ---: | ---: | :---: | --- |",
    ]
    for outcome in best.outcomes:
        rank = outcome.first_relevant_rank
        top = f"{outcome.top_score:.3f}" if outcome.top_score is not None else "-"
        lines.append(
            f"| {outcome.question_id} | {', '.join(outcome.expected)} | "
            f"{rank if rank is not None else '-'} | {top} | "
            f"{'yes' if outcome.answered() else 'no'} | {outcome.question} |"
        )
    lines.append("")
    return "\n".join(lines)


# --- CLI -------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--embedding", choices=("gemini", "hashing"), default="gemini")
    parser.add_argument("--chunk-sizes", type=int, nargs="+", default=list(DEFAULT_CHUNK_SIZES))
    parser.add_argument("--thresholds", type=float, nargs="+", default=list(DEFAULT_THRESHOLDS))
    parser.add_argument("--top-ks", type=int, nargs="+", default=list(DEFAULT_TOP_KS))
    parser.add_argument("--candidates", type=int, default=DEFAULT_CANDIDATES)
    parser.add_argument("--rerank-top-k", type=int, default=DEFAULT_RERANK_TOP_K)
    parser.add_argument(
        "--rerank",
        choices=("on", "off", "both"),
        default="on",
        help="Run with the Cross Encoder on, off, or both (AI-162 comparison).",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--json", type=Path, default=None, help="Optional machine-readable output.")
    parser.add_argument(
        "--qdrant",
        choices=("memory", "server"),
        default="memory",
        help="Index into an embedded collection (default) or the configured Qdrant server.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.monotonic()

    payload = json.loads(args.questions.read_text(encoding="utf-8"))
    questions = payload["questions"]
    out_of_scope = payload.get("out_of_scope", [])
    documents = load_corpus(args.corpus)

    embedder = build_embedder(args.embedding)
    embedder_name = getattr(embedder, "name", None) or getattr(embedder, "_model", args.embedding)

    rerank_modes = {"on": (True,), "off": (False,), "both": (True, False)}[args.rerank]

    results: list[ConfigurationResult] = []
    for chunk_size in args.chunk_sizes:
        chunks = chunk_corpus(documents, chunk_size)
        store = build_store(chunks, embedder, in_memory=args.qdrant == "memory")
        for rerank in rerank_modes:
            # Cache (ranked, latency) so the expensive rerank runs once per
            # question while every configuration still records the real cost.
            cache: dict[str, tuple[list[RankedChunk], float]] = {}

            def retrieve_fn(
                question: str, _store=store, _cache=cache, _rerank=rerank
            ) -> tuple[list[RankedChunk], float]:
                if question not in _cache:
                    started = time.perf_counter()
                    ranked = retrieve(
                        _store,
                        embedder,
                        question,
                        candidates=args.candidates,
                        rerank_top_k=max(args.rerank_top_k, max(args.top_ks)),
                        rerank=_rerank,
                    )
                    _cache[question] = (ranked, (time.perf_counter() - started) * 1000.0)
                return _cache[question]

            for threshold in args.thresholds:
                for top_k in args.top_ks:
                    results.append(
                        evaluate_configuration(
                            chunk_size=chunk_size,
                            threshold=threshold,
                            top_k=top_k,
                            questions=questions,
                            out_of_scope=out_of_scope,
                            retrieve_fn=retrieve_fn,
                            chunk_count=len(chunks),
                            rerank=rerank,
                        )
                    )
        print(f"chunk_size={chunk_size}: {len(chunks)} chunks indexed", file=sys.stderr)

    best = max(results, key=lambda r: (r.hit_rate, r.mrr, -r.false_not_found_rate, r.top_k))
    elapsed = time.monotonic() - started
    report = render_report(
        embedder_name=embedder_name,
        question_count=len(questions),
        out_of_scope_count=len(out_of_scope),
        results=results,
        best=best,
        elapsed_seconds=elapsed,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "embedder": embedder_name,
                    "questions": len(questions),
                    "results": [result.as_dict() for result in results],
                    "best": best.as_dict(),
                    "rerank_comparison": rerank_comparison(results),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
