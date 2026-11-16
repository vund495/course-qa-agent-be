# AI-190 — Chat context token budget

## Purpose and delivery

Keep answer-generation prompts inside an explicit token budget, including a reserved output budget. The acceptance scenario is a **20-turn conversation**, not 30 turns. Twenty stored turns do not require sending all twenty turns to the model.

This is a backend-only change. The existing SSE `error`, `token`, `citation`, and `done` contracts remain in use. There is no database migration, frontend change, new dependency, or automatic Jira transition.

Both branches start at `ad8e3ea1ee5cea816b9649ba963067fe464afcca` (`origin/main`). This repository has no `develop` branch.

| Branch | Contents |
| --- | --- |
| `features/Implementation_ChatContextTokenBudget` | Backend code, configuration, tests, benchmark script |
| `features/Design_ChatContextTokenBudget` | This design and validation record |

Implementation changes live in the normal backend checkout, reached through `course-qa-workspace/be`. The separate design worktree lives inside the workspace at `.worktrees/ai190-design`. The Vietnamese implementation plan is stored at `resources/plans/ai-190-chat-context-token-budget-plan.md` in the workspace.

## Configuration and invariants

| Environment variable | Default | Meaning |
| --- | ---: | --- |
| `CHAT_INPUT_MAX_TOKENS` | 24000 | Maximum counted final input |
| `CHAT_SYSTEM_MAX_TOKENS` | 6000 | System instruction cap |
| `CHAT_HISTORY_MAX_TOKENS` | 4000 | Conversation history cap |
| `CHAT_DOCUMENTS_MAX_TOKENS` | 12000 | Retrieved evidence, web sources and syllabus cap |
| `CHAT_ANSWER_MAX_TOKENS` | 4000 | Provider output-token limit |
| `CHAT_TOKEN_SAFETY_MARGIN` | 1000 | Reserve for provider framing/tokenization differences |
| `CHAT_TOKEN_COUNT_TIMEOUT_SECONDS` | 5 | Per-call timeout, at most 15 seconds |

All caps must be positive. Each input-section cap must not exceed the total input cap. Section caps are ceilings, not preallocated minimums; the question, student code, source labels, template delimiters and final instructions share the total input budget.

The effective input ceiling is:

```text
effective_input = min(CHAT_INPUT_MAX_TOKENS,
                      model.input_token_limit
                      - CHAT_ANSWER_MAX_TOKENS
                      - CHAT_TOKEN_SAFETY_MARGIN)
```

The configured answer cap must also fit the model's output limit. Invalid model metadata or an impossible budget fails before answer generation.

The rolling history window defaults to **20 complete question/answer exchanges** (`CHAT_CONTEXT_EXCHANGES=20`). After exchange 20, new turns continue using the latest 20 exchanges. A 30,000-character safety cap prevents oversized history from reaching prompt fitting; token-budget fitting may further remove the oldest exchanges when required by the model input ceiling. The history helper never splits an exchange or user-supplied `Student:` text.

## Data flow and truncation

1. Retrieve evidence and construct the existing answer prompt for the selected route.
2. Keep prompt inputs available for re-rendering. Preserve final branch-specific tutoring rules and the language mandate.
3. Resolve the active Gemini model and key through the existing key pool. Fetch and cache the model's input/output limits.
4. Count system, history, evidence and the complete rendered prompt through the existing Google GenAI SDK.
5. If necessary, remove the oldest complete exchanges, then the lowest-priority evidence. Retrieval scores order course sources; ties retain earlier sources. Web results retain their existing relevance order. Structured syllabus information keeps its existing priority.
6. If only the highest-priority source remains and is too long, keep a UTF-8-safe prefix with a `[truncated]` suffix, preserving source identity and metadata. If even a nonempty source cannot fit, return a controlled error.
7. Re-render retained documents first and web results second, with contiguous citation numbers. Count the final prompt after every instruction has been applied.
8. Send only validated messages to generation, with the configured provider output-token cap.

The mandatory question, student code, system rules and language instruction are never truncated. Prompt fitting changes only request-local copies. Persisted history and original documents remain intact.

Once an exact provider count establishes that trimming is necessary, UTF-8 byte lengths guide a conservative selection without a network request per exchange or chunk. This can retain less context than an exhaustive token search. **Byte lengths are not treated as Gemini token measurements**: final section counts and the final rendered-prompt count must still pass the provider check.

The Gemini Developer API does not support `system_instruction` in `CountTokensConfig` in the installed SDK. Its text is therefore included in the counted contents alongside the rendered user message. The 1000-token safety margin covers differences from the generation request's role framing. Provider usage metadata from the live benchmark should be compared with preflight counts; exact equality is not assumed.

## Citations, resilience and compatibility

Retained source objects drive all three representations: prompt source labels, emitted SSE citations and citations saved with the completed answer. Truncated evidence is also used for passage matching. Metadata such as document ID and page remains attached. Web indexes begin after the number of retained document chunks, even when final document citation chips are grouped.

Token operations use at most eight `count_tokens` attempts across key rotation and model fallback. Their cumulative active I/O allowance is fifteen seconds; a fallback does not reset it. Metadata calls consume the same time allowance, have the same per-call timeout, and have a bounded key-attempt loop. Generation waiting does not consume the token-counting I/O allowance. Each prompt-fitting stage also has a fifteen-second wall-clock timeout.

Key errors, rate limits and transient provider failures use the existing key failure/cooldown handling and auto-switch preference. Specific invalid-credential HTTP 400 errors rotate; arbitrary malformed-request HTTP 400 errors do not. No token estimate is used to bypass an unavailable counting API.

The initial validated model is not counted again before its first answer attempt. Before switching models, the gateway checks the already-fitted prompt and output reserve against the fallback model's limits using the remaining shared allowance. If the allowance is exhausted or the fallback cannot fit, generation stops with a controlled error instead of sending an unchecked prompt.

Missing credentials, metadata failures, exhausted counting allowances and oversized mandatory input produce an SSE `error` through the existing contract. A failed validation never begins answer streaming or persists a completed answer. Existing gateway callers that do not request an output cap retain their previous behavior.

Each token truncation logs the section, before/after token count, dropped token count, number of removed items, model, effective budget and elapsed time. Logs do not include question text, history, document contents or API keys. Existing character-based history loading remains a separate upstream compatibility limit.

## Validation record

Baseline focused checks at `ad8e3ea`: **25 passed** across chat context, chat service and gateway rotation.

New automated checks cover:

- Twenty-turn history, oldest-first removal and complete exchange boundaries.
- Inclusive token-cap boundaries and oversized mandatory input.
- High-score evidence retention, safe single-source truncation and source identity.
- Final tutoring/language instructions, student code and citation renumbering.
- Full chat streaming with twenty history turns and a removed low-score source.
- Counting failure producing an SSE error before answer streaming.
- Exact-text count caching, timeout, eight-call cap and shared fallback allowance.
- Invalid/rate-limited key rotation without resetting allowances.
- Output-cap forwarding and rejection of a fallback with insufficient context.
- Table evidence truncation without re-inserting discarded table headers during re-rendering.

A deterministic policy test uses **UTF-8 bytes as fake test units**, not real Gemini tokens:

| Measurement | Before | After |
| --- | ---: | ---: |
| History pairs | 20 | 1 |
| Rendered prompt test units | 844 | 66 |
| Configured test cap | 180 | 180 |

This test proves the selection invariant under an intentionally small budget. It is not a production quality or latency benchmark. The streaming integration test separately verifies that a twenty-turn input completes with the retained source's correct citation.

The environment key was rejected with **HTTP 401**. A subsequent read-only lookup found a working active key in the existing admin key pool. The synthetic twenty-turn benchmark then completed with `models/gemini-3.5-flash-lite`; both the original and fitted prompts produced nonempty answers without a context-length error. No credential values were printed or saved, and the benchmark did not update key records.

| Live measurement | Before | After |
| --- | ---: | ---: |
| Supplied history pairs retained | 20 | 1 |
| Preflight counted prompt tokens | 10946 | 2976 |
| Provider-reported prompt tokens | 10947 | 2977 |
| Generation latency | 1423.4 ms | 988.5 ms |
| Nonempty answer received | Yes | Yes |

Fitting took **1094.8 ms** and **7 counting calls**. The after case therefore took approximately **2083.3 ms** for fitting plus generation; counting introduces latency even though this sample's shorter generation was faster. This is one sample, not a p95 performance claim or a quality comparison. Provider usage was one token above preflight counting in both cases, within the configured safety reserve.

Run the reproducible synthetic twenty-turn benchmark from the backend checkout (`be/`):

```bash
PYTHONPATH=. python scripts/benchmark_chat_token_budget.py
# Optionally supply --env-file /path/to/.env and/or --model <available-model>.
```

Activate the existing backend virtual environment (`be/.venv`) before running the command. The script prints counts and before/after generation latency, never prompts, answers or credentials. The standalone command accepts an environment key; the recorded run supplied the working pool credential to the same benchmark in memory. To reproduce it, use a valid environment credential for the same model. It measures prompt fitting and generation, not the full HTTP/retrieval pipeline, and deliberately exercises twenty supplied history pairs before the legacy loading cap.

For offline regression validation, unset API-key variables in the test process so the repository's existing real-API tests skip naturally:

```bash
env -u GEMINI_API_KEY -u GOOGLE_API_KEY python -m pytest -q
```

Do not set these variables to empty strings: the settings tests explicitly verify environment alias precedence, and an empty `GOOGLE_API_KEY` overrides their temporary `GEMINI_API_KEY` value.

Final focused validation: **232 passed** across chat services, chat router and LLM/gateway tests, including the AI-190 token-budget cases. The two latest regression tests also passed in isolation. Ruff checks on changed Python files and `git diff --check` passed. Review findings about key rotation, shared fallback allowance, duplicate syllabus roadmap citations, and the fallback input cap were fixed and rechecked. A prior full backend suite completed with **1071 passed, 2 skipped, 2 failed, and 33 warnings** in **395.07 seconds**. The two failures were existing real-API Gemini embedding tests, both rejected with HTTP 401 because the configured API key was invalid. They do not exercise AI-190. Warnings concern existing FastAPI/Starlette status-code naming and Alembic configuration.

The current focused run covered the latest AI-190 changes. The full-suite result is not fully green because of the two unrelated live Gemini embedding authentication failures above; rerun those tests with a valid API key to verify the existing real-API checks.

AC-05 has both an offline full-stream integration check and the live synthetic twenty-turn fitting/generation check above. This does not claim an end-to-end HTTP/browser test or answer-quality evaluation. The implementation and design changes are maintained on separate branches. Jira was not closed as part of this work.
