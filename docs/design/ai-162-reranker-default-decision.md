# AI-162 — The reranker default, decided by measurement

> **Ticket:** AI-162 (Epic E4, retrieval quality) · **Status:** Implemented
> **Branch:** `features/Implementation_RerankerDefaultDecision`
> **Related stories:** AI-61 (RAG Q&A backend), AI-65 (retrieval score
> threshold), AI-161 (retrieval parameter tuning).

## Purpose

The Cross Encoder reranker (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`) ran on
every class-material question, but nobody had measured what it bought or what it
cost. This story runs the AI-161 evaluation set with the reranker on and off,
records quality and latency for both, and sets the default from the data.

## Method (AC-01)

The AI-161 harness (`eval/retrieval/run_eval.py`) gained a `--rerank on|off|both`
flag. `off` mirrors `RERANKER_ENABLED=false`: the Cross Encoder is skipped and the
vector-store order and raw cosine scores are kept. Everything else — corpus,
chunking, `gemini-embedding-2`, the 30 questions and 4 off-topic probes — is
identical between the two runs.

```bash
uv run python eval/retrieval/run_eval.py --embedding gemini --rerank both \
  --chunk-sizes 800 --thresholds 0.45 --top-ks 3 5 10 \
  --report eval/retrieval/results/ai-162-reranker.md \
  --json  eval/retrieval/results/ai-162-reranker.json
```

The run uses the AI-161 final configuration (`chunk_size=800`,
`threshold=0.45`), so the comparison isolates the reranker.

## Measured results (AC-02)

| Metric | Reranker on | Reranker off | Delta |
| --- | ---: | ---: | ---: |
| Hit-rate@3 | 100.0% | 100.0% | 0 |
| MRR | 1.000 | 1.000 | 0 |
| False "not found" rate | 26.7% | 0.0% | −26.7 pts |
| Out-of-scope rejection | **100.0%** | **0.0%** | **−100 pts** |
| Mean top score | 0.669 | 0.726 | +0.057 |
| p50 latency | 1118.5 ms | 430.3 ms | +688 ms |
| p95 latency | 2167.4 ms | 853.2 ms | +1314 ms |

`top_k` 3, 5 and 10 produce identical numbers in both modes, so the table shows
one row per mode. The full report is in `eval/retrieval/results/ai-162-reranker.md`.

### Why the off-topic row decides it

Hit-rate and MRR are already 1.000 without the reranker: on this corpus the
embedding search alone puts the right document first. The reranker's value is not
ranking — it is **calibration**. The same four off-topic probes score:

| Probe | Reranker on | Reranker off |
| --- | ---: | ---: |
| x01 "What is the capital of France?" | 0.001 | 0.545 |
| x02 "How do I deploy a Django application to AWS Lambda?" | 0.010 | 0.542 |
| x03 "What is the time complexity of Dijkstra's algorithm?" | 0.000 | 0.550 |
| x04 "Giá vàng hôm nay là bao nhiêu?" | 0.000 | 0.500 |

Raw cosine similarity is high for *any* text against a 168-chunk corpus — every
off-topic question lands at 0.50–0.55, comfortably above the 0.45 threshold. With
the reranker off, **every off-topic question would be answered from course
material**. The reranker is the only component that separates in-scope from
out-of-scope, and the AI-161 threshold was tuned for its score distribution.

The 0.0% false "not found" rate in the off run is not a win: it happens because
raw cosine scores are uniformly high, so the threshold stops discriminating at
all. A threshold that accepts everything is not a threshold.

## Decision (AC-03)

**The reranker stays on by default** (`RERANKER_ENABLED=true`).

The measured gain is correctness, not ranking: 100% off-topic rejection versus
0%. The cost is +688 ms at p50 and +1314 ms at p95 on CPU. That is a real cost —
it is the single largest latency item in the retrieval path — but it buys the
difference between "answers only from class material" and "answers anything from
class material", which is the product's core promise.

The cost is also bounded and already mitigated:

- The AI-65 fail-fast path skips the Cross Encoder entirely when the best
  candidate is below `unrelated_threshold`, so off-topic turns do not pay it.
- The model is warmed up at startup (`reranker_service.warm_up`), so the first
  request does not pay the load.
- A GPU host moves the same work off the CPU; the numbers above are CPU-only.

If a deployment cannot afford the latency, the honest trade is to turn the
reranker off **and** stop trusting the threshold — not to keep the threshold and
remove the component that makes it meaningful.

## The toggle stays available (AC-04)

`RERANKER_ENABLED` (env, default `true`) is read by
`reranker_service.rerank_all`, which returns the candidates unchanged when it is
false. `warm_up` also skips loading the model, so a disabled deployment does not
pay the startup cost. The setting is documented in `.env.example`.

This is a deployment-level switch, not a per-class admin setting: the reranker
is a process-wide model, and a per-class toggle would make the same question
route differently depending on which class asked it.

## Known limitation

The 26.7% false "not found" rate is unchanged from AI-161 and is not addressed
here. Those eight questions are retrieved at rank 1 but score below 0.45 because
the Cross Encoder rates terse slide bullets low against a full question. Fixing
that needs a different reranker or a prompt change, tracked separately.

## Verification

```bash
uv run python eval/retrieval/run_eval.py --embedding gemini --rerank both
uv run pytest tests/eval tests/services/chat/test_reranker_service.py -q
uv run pytest -q
uv run ruff check .
```
