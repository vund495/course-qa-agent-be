# AI-161 — Retrieval parameters chosen from measured evidence

> **Ticket:** AI-161 (Epic E4, retrieval quality) · **Status:** Implemented
> **Branch:** `features/Implementation_RetrievalParameterTuning`
> **Related stories:** AI-51 (document chunking), AI-53 (embedding + Qdrant),
> AI-61 (RAG Q&A backend), AI-65 (retrieval score threshold), AI-107
> (embedding/retrieval configuration).

## Purpose

The retrieval parameters — chunk size, similarity threshold, and `top_k` — were
previously defaults chosen by intuition (`CHUNK_SIZE=800`, `RETRIEVAL_TOP_K=3`,
`RETRIEVAL_THRESHOLD=0.80`). This story replaces that guesswork with a fixed,
re-runnable evaluation set and a written rationale for the configuration that
ships.

Nothing in the production request path changed: the harness drives the same
chunkers, the same `QdrantStore`, the same `rag_service.retrieve_class_chunks`
guard, and the same Cross Encoder reranker that serve students.

## Evaluation set (AC-01)

| Artifact | Path |
| --- | --- |
| Fixed question set | `eval/retrieval/questions.json` |
| Corpus (six Python course decks) | `eval/retrieval/corpus/*.md` |
| Harness | `eval/retrieval/run_eval.py` |
| Latest report | `eval/retrieval/results/latest.md` |

The set holds **30 real student questions** (English and Vietnamese) plus **4
out-of-scope probes**. Every question names the corpus file(s) that legitimately
answer it; a hit is any expected file appearing in the top-k. The corpus is the
Markdown produced by the production loaders and cleaner for the six slide decks
in `materials/courses-for-agent/Slides`, so chunk boundaries and metadata match
what ingestion produces for a real upload.

One command runs everything:

```bash
uv run python eval/retrieval/run_eval.py            # Gemini embeddings (production)
uv run python eval/retrieval/run_eval.py --embedding hashing   # offline, no key
```

The harness needs no Postgres and no Qdrant server: it indexes into an embedded
Qdrant collection through the production `QdrantStore`, and replaces the AI-39
"retrievable document" DB guard with the corpus manifest.

## Metrics (AC-02)

| Metric | Definition |
| --- | --- |
| Hit-rate | Share of questions whose expected document appears in the top-k. |
| MRR | Mean reciprocal rank of the first expected document (0 when absent). |
| False "not found" rate | Share of in-scope questions whose best reranked score is below the threshold, so the router would refuse to answer from documents. |
| Out-of-scope rejection | Share of off-topic probes correctly refused (guard against a threshold so low that everything is "found"). |

The false "not found" rate is the metric that makes a threshold sweep meaningful:
hit-rate and MRR are threshold-independent, while the threshold decides whether a
correctly retrieved passage is actually used.

## Sweep (AC-03)

`chunk_size ∈ {600, 800, 1000}` × `threshold ∈ {0.30, 0.45, 0.60}` ×
`top_k ∈ {3, 5, 10}` = 27 configurations, each scored against all 30 questions
and 4 probes. The full table is in `eval/retrieval/results/latest.md`.

Measured with `gemini-embedding-2` (the production embedder) and the production
Cross Encoder `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, 466 s wall clock.

| chunk_size | threshold | top_k | chunks | hit-rate | MRR | false not-found | out-of-scope rejection | mean top score |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 600 | 0.30 | 3 / 5 / 10 | 174 | 100.0% | 1.000 | 23.3% | 100.0% | 0.674 |
| 600 | 0.45 | 3 / 5 / 10 | 174 | 100.0% | 1.000 | 26.7% | 100.0% | 0.674 |
| 600 | 0.60 | 3 / 5 / 10 | 174 | 100.0% | 1.000 | 30.0% | 100.0% | 0.674 |
| 800 | 0.30 | 3 / 5 / 10 | 168 | 100.0% | 1.000 | 23.3% | 100.0% | 0.669 |
| 800 | 0.45 | 3 / 5 / 10 | 168 | 100.0% | 1.000 | 26.7% | 100.0% | 0.669 |
| 800 | 0.60 | 3 / 5 / 10 | 168 | 100.0% | 1.000 | 33.3% | 100.0% | 0.669 |
| 1000 | 0.30 | 3 / 5 / 10 | 168 | 100.0% | 1.000 | 23.3% | 100.0% | 0.674 |
| 1000 | 0.45 | 3 / 5 / 10 | 168 | 100.0% | 1.000 | 26.7% | 100.0% | 0.674 |
| 1000 | 0.60 | 3 / 5 / 10 | 168 | 100.0% | 1.000 | 30.0% | 100.0% | 0.674 |

`top_k` did not move any metric: the Cross Encoder already puts the expected
document at rank 1 for all 30 questions (MRR 1.000), so widening the window from
3 to 10 adds no hit. `top_k` therefore stays at the production default of 3.

### What the sweep says

1. **Chunk size is not the bottleneck.** 600, 800, and 1000 chars all reach
   hit-rate 100% / MRR 1.000. The decks are slide-shaped: most slides are already
   under 600 characters, so the three sizes produce nearly the same 168–174
   chunks. There is no measured reason to move away from the shipped 800.
2. **The threshold is the only lever that moves the false "not found" rate.**
   It rises monotonically with the threshold: 23.3% → 26.7% → 30.0%.
3. **The reranker, not the threshold, is what separates in-scope from
   out-of-scope.** All four off-topic probes score far below every in-scope
   question at every threshold, so the out-of-scope rejection rate is 100% in
   all 27 configurations.

### The production threshold (0.80) is too strict

The sweep brackets the shipped default. Re-scoring the same measured per-question
scores at `threshold = 0.80` (the AI-65 default) gives:

| threshold | in-scope questions answered | false "not found" rate |
| ---: | ---: | ---: |
| 0.30 | 23 / 30 | 23.3% |
| 0.45 | 22 / 30 | 26.7% |
| 0.60 | 21 / 30 | 30.0% |
| **0.80 (shipped)** | **12 / 30** | **60.0%** |

At 0.80 the router refuses to answer **18 of 30** questions whose expected
document was retrieved at rank 1. The failures are not retrieval misses — they
are correct passages scored below 0.80 by the Cross Encoder (for example q27
"startswith" at 0.799, q12 dictionary deletion at 0.785, q16 while loop at 0.771).
The shipped default was tuned for raw cosine similarity, but AI-65 now thresholds
on the calibrated Cross Encoder score, whose distribution sits lower.

## Final configuration and rationale (AC-04)

| Parameter | Value | Evidence |
| --- | --- | --- |
| `CHUNK_SIZE` | **800** (unchanged) | 600/800/1000 all score hit-rate 100% / MRR 1.000; 800 keeps the shipped value and the fewest chunks (168). |
| `RETRIEVAL_THRESHOLD` | **0.45** (was 0.80) | The measured plateau (0.30–0.60) holds the false "not found" rate at 23–30%, against 60% at the shipped 0.80. 0.45 is the middle of that plateau and the documented `unrelated_threshold` default. |
| `RETRIEVER_TOP_K` | **3** (unchanged) | MRR is 1.000 at top_k 3; 5 and 10 add no hit. |

The change is a default, not a hard-coded value: `retrieval_threshold` stays
admin-configurable through `PATCH /api/admin/retrieval-config` (AI-65 AC-05), so
a class whose material scores differently can be re-tuned without a deploy.

**Why 0.45 and not 0.30.** Both sit on the same plateau for this corpus, and
0.30 is 3.4 points better on the false "not found" rate. It is rejected because
it is the bottom edge of the plateau: a single unseen question scoring just
below it would fall through, and the off-topic probes already score near zero, so
there is no separation to gain. 0.45 keeps the middle of the measured band and
matches the documented `unrelated_threshold` default.

**Known limitation.** Eight questions (q05, q13, q14, q15, q17, q19, q22, q29)
are retrieved at rank 1 but still score below 0.45. They are short, terse slide
bullets ("Lists can be nested", "Membership operators") that the Cross Encoder
scores low against a full question. Lowering the threshold further would not fix
them without also letting off-topic questions through; the honest fix is a
reranker or prompt change, tracked separately.

**Re-running.** The numbers above come from `gemini-embedding-2`. The free tier
allows 1000 embedding requests per day, and one full sweep uses roughly that
much, so a re-run may need to wait for the daily reset or use a paid key. The
harness also runs offline with `--embedding hashing` for a fast regression check
of the wiring (the hashing embedder is lexical, so its absolute numbers are not
comparable to Gemini's).

## Verification

```bash
uv run python eval/retrieval/run_eval.py
uv run pytest tests/eval -q
uv run pytest -q
uv run ruff check .
```
