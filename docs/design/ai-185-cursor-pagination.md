# AI-185 — Cursor pagination for chat history (API Design)

> **Ticket:** [AI-185](https://ai03.atlassian.net/browse/AI-185) (Epic [AI-93](https://ai03.atlassian.net/browse/AI-93): Chat History & Memory)
> **Priority:** Medium · **Status:** Design
> **Assignee:** Bui Trong Suu
> **Branch:** `features/Design_ChatHistoryCursorPagination`
> **Related stories:** AI-95 (Save & Display Chat History), AI-97 (Reopen an Old Conversation), AI-99 (Delete Chat History), AI-101 (Search Chat History).

---

## 1. Purpose

The chat-history sidebar currently loads **one page of sessions** through
`GET /api/history` with `limit`/`offset`. The frontend does not pass either
parameter, so it always receives the backend default of **50 rows** and has no
way to reach older conversations. When a student has hundreds of sessions:

- scrolling back through old chat is impossible (the list simply ends at 50),
- and if the client ever implements paging with `OFFSET`, rows shift while the
  student scrolls — a session that receives a new message jumps to the top of
  the `updated_at DESC` order and the next `OFFSET` page **skips one row** and
  **repeats another**.

This story adds **keyset (cursor) pagination** for the session list, while
keeping the existing `OFFSET` endpoint byte-for-byte compatible so the current
frontend does not break.

### 1.1 Acceptance criteria (Jira AI-185)

| AC | Requirement | How this design satisfies it |
|---|---|---|
| **AC-01** | Cursor pagination exists, cursor encodes the `(created_at, id)` pair | ⚠️ **Deviation** — the cursor encodes the **column the query actually sorts on**: `(updated_at, id)` for the `recent` section and `(pinned_at, id)` for the `pinned` section. See §1.3. |
| **AC-02** | The existing `OFFSET` endpoint keeps working exactly as before | `section` is optional; when it is absent the router calls the untouched `get_sessions_by_class()` |
| **AC-03** | The response includes `next_cursor`, set to `null` on the last page | `ChatSessionListResponse.next_cursor: str \| None = None` |
| **AC-04** | Ordering is stable when several rows share a timestamp, using `id` as the tiebreaker | `ORDER BY <ts> DESC, id DESC` and a keyset predicate that compares `id` on ties |
| **AC-05** | Paging through every page yields no duplicates and nothing missing compared with a full query | `test_cursor_sweep_returns_every_session_once` |
| **AC-06** | A row inserted mid-pagination causes neither a duplicate nor a gap | `test_cursor_insert_between_pages_has_no_duplicate_or_gap` |
| **AC-07** | Deep-page timing is measured before and after and no longer grows linearly | `scripts/benchmark_history_pagination.py` (§8) |
| **AC-08** | The full backend suite stays green | `pytest -q` |

### 1.2 In scope

- A new `section` + `cursor` query pair on `GET /api/history`.
- A new service function `get_sessions_cursor()` beside the existing one.
- A new `next_cursor` field on the list response (default `null`).
- Two composite indexes on `chat_session`.
- A benchmark script that records deep-page timing.

### 1.3 Out of scope

- Cursor pagination for `GET /api/history/search` (AI-101) — that endpoint keeps
  `limit`/`offset`.
- Cursor pagination for the messages inside one session
  (`GET /api/history/{session_id}`) — it returns the full transcript by design.
- Any change to `sortSessionsWithPinned()` on the client.
- Any change to the `OFFSET` code path.

### 1.4 Deviation from AC-01, and why

AC-01 names `(created_at, id)`. That pair is **wrong for this query**, and using
it would return incorrect pages.

The list is ordered by `updated_at`, not `created_at`
(`app/services/history_service.py::get_sessions_by_class`):

```python
.order_by(
    ChatSession.is_pinned.desc(),
    ChatSession.pinned_at.asc().nullslast(),
    ChatSession.updated_at.desc(),
    ChatSession.created_at.desc(),
)
```

A keyset cursor is only correct when it encodes **the same tuple the `ORDER BY`
uses**. If the cursor carried `created_at` while the query sorted by
`updated_at`, the predicate `created_at < cursor.created_at` would select rows
that are not adjacent in the result order — producing both duplicates and gaps.

| Section | Sort column | Direction | Tiebreaker | Why this column |
|---|---|---|---|---|
| `recent` | `updated_at` | `DESC` | `id DESC` | Sidebar shows the most recently active conversation first |
| `pinned` | `pinned_at` | `ASC` | `id ASC` | Pinned block is FIFO — the oldest pin stays on top, matching `sortSessionsWithPinned()` |

`created_at` is immutable, which makes it an attractive cursor key in general.
Here it is unusable because the product orders by activity, not creation. The
deviation is recorded here and in the MR description.

**Known consequence.** AC-06 ("a row inserted mid-pagination causes no duplicate
or gap") holds for a **newly created** session. For a session that is
**updated** while the student is paging, it can move above the cursor and be
skipped on the next page. This is inherent to keyset pagination on a mutable
column and is accepted: the frontend only pages deeper while the student
scrolls, and the conversation being actively chatted in is always at the top of
the list.

### 1.5 Why two cursors instead of one

The sidebar renders **two independent blocks**
(`features/history/chat-history-sidebar.tsx`):

```tsx
const pinnedSessions = sessions.filter((s) => s.is_pinned);
const recentSessions = sessions.filter((s) => !s.is_pinned);
```

They sort in **opposite directions** (`pinned_at ASC` vs `updated_at DESC`). A
single cursor cannot describe a position in both orders, so the API exposes a
`section` parameter and the client keeps one cursor per section.

---

## 2. API contract

### 2.1 Request

- **Method:** `GET`
- **URL:** `/api/history`
- **Auth:** `Authorization: Bearer <JWT_ACCESS_TOKEN>`
- **Request body:** none

#### Query parameters

| Parameter | Type | Required | Default | Validation | Description |
|---|---|:---:|:---:|---|---|
| `class_id` | `UUID` | No | `None` | valid UUID | Restrict the list to one class |
| `limit` | `integer` | No | `50` | `ge=1`, `le=100` | Rows per page (cursor mode uses `20` from the client) |
| `offset` | `integer` | No | `0` | `ge=0` | **Legacy mode only.** Ignored when `section` is present |
| `section` | `string` | No | `None` | `recent` \| `pinned` | Selects the cursor mode and the sort order |
| `cursor` | `string` | No | `None` | opaque, base64url | Position returned as `next_cursor` by the previous page |

**Mode selection**

| `section` | `cursor` | Behaviour |
|---|---|---|
| absent | absent | **Legacy OFFSET mode** — unchanged code path (AC-02) |
| absent | present | `400` — a cursor is meaningless without a section |
| present | absent | First page of that section |
| present | present | Next page of that section |

### 2.2 Success response — cursor mode

**Status:** `200 OK` · **Schema:** `ChatSessionListResponse`

```json
{
  "items": [
    {
      "id": "a2c3d4e5-f6a7-48b9-80c1-d2e3f4a5b6c7",
      "class_id": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
      "title": "Thuật toán tìm kiếm theo chiều rộng BFS",
      "created_at": "2026-11-20T09:14:02.113000Z",
      "updated_at": "2026-11-20T10:05:41.882000Z",
      "is_pinned": false,
      "pinned_at": null
    }
  ],
  "total": 137,
  "next_cursor": "eyJ2IjoxLCJzIjoicmVjZW50IiwidCI6IjIwMjYtMTEtMjBUMTA6MDU6NDEuODgyMDAwKzAwOjAwIiwiaWQiOiJhMmMzZDRlNS1mNmE3LTQ4YjktODBjMS1kMmUzZjRhNWI2YzcifQ"
}
```

`next_cursor` is `null` when the returned page is the last one.

### 2.3 Success response — legacy mode

Identical to today, plus `"next_cursor": null`:

```json
{
  "items": [ ... ],
  "total": 137,
  "next_cursor": null
}
```

The extra field is additive. A client that ignores it sees no change (AC-02).

### 2.4 Error responses

| Code | Condition | Body |
|---|---|---|
| `400` | `cursor` present without `section` | `{"detail": "cursor requires section."}` |
| `400` | Cursor is not valid base64url/JSON | `{"detail": "Malformed cursor."}` |
| `400` | Cursor version is not `1` | `{"detail": "Unsupported cursor version."}` |
| `400` | Cursor belongs to the other section | `{"detail": "Cursor does not belong to this section."}` |
| `401` | Missing or invalid token | standard auth error |
| `422` | `section` not in `{recent, pinned}` | FastAPI validation error |
| `422` | `limit` outside `1..100` | FastAPI validation error |

### 2.5 Row-level security

Every cursor query is filtered by `ChatSession.user_id == current_user.id`
before the keyset predicate is applied. A cursor issued to one user therefore
cannot reach another user's rows: the `user_id` filter is part of the same
`WHERE` clause, not a post-filter.

---

## 3. Cursor format

### 3.1 Payload

```json
{ "v": 1, "s": "recent", "t": "2026-11-20T10:05:41.882000+00:00", "id": "a2c3d4e5-..." }
```

| Key | Meaning |
|---|---|
| `v` | Format version. Lets a future change be detected instead of silently mis-parsed |
| `s` | Section (`recent` \| `pinned`). Rejects a cursor reused against the other section |
| `t` | ISO-8601 timestamp of the sort column (`updated_at` or `pinned_at`), timezone-aware |
| `id` | UUID tiebreaker for rows that share `t` |

### 3.2 Encoding

`base64url(json, separators=(",", ":"))` with `=` padding stripped — URL-safe,
no escaping needed in a query string.

```python
def encode_cursor(section: str, timestamp: datetime, row_id: uuid.UUID) -> str:
    payload = {"v": 1, "s": section, "t": timestamp.isoformat(), "id": str(row_id)}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
```

### 3.3 Why the cursor is opaque

The client must not construct or interpret cursors. Keeping the payload
base64url-encoded means:

- the internal sort columns can change without a client change,
- a malformed or hand-edited cursor fails loudly (`400`) instead of producing a
  silently wrong page,
- the version byte gives a migration path if the payload shape ever changes.

### 3.4 Keyset predicate

For a `DESC` section (`recent`):

```sql
WHERE user_id = :uid
  AND is_pinned = false
  AND ( updated_at < :t  OR  (updated_at = :t AND id < :id) )
ORDER BY updated_at DESC, id DESC
LIMIT :limit + 1
```

For an `ASC` section (`pinned`):

```sql
WHERE user_id = :uid
  AND is_pinned = true
  AND pinned_at IS NOT NULL
  AND ( pinned_at > :t  OR  (pinned_at = :t AND id > :id) )
ORDER BY pinned_at ASC, id ASC
LIMIT :limit + 1
```

The `OR` form is used instead of a row-value comparison `(a, b) < (x, y)`
because the test suite runs on **SQLite** (`TEST_DB_URL = "sqlite://"`), which
does not support row-value comparison. The `OR` form is portable and produces
the same plan on PostgreSQL.

### 3.5 Detecting the last page

The service requests `limit + 1` rows. If `limit + 1` rows come back, one extra
row exists, so the page is not the last: the extra row is dropped and
`next_cursor` is encoded from the **last row of the returned page**. If exactly
`limit` (or fewer) rows come back, `next_cursor` is `null`.

This avoids a second `COUNT` query per page and avoids the "empty last page"
that an off-by-one produces.

---

## 4. OFFSET vs KEYSET

| Aspect | `OFFSET` (current) | `KEYSET` (this story) |
|---|---|---|
| Query cost at page *n* | `O(offset + limit)` — the database scans and discards every skipped row | `O(log n + limit)` — index seek to the cursor position |
| Deep page timing | Grows linearly with `offset` | Effectively flat |
| Insert during paging | Row shifts the window → **duplicate + gap** | No duplicate; a row *updated* above the cursor may be skipped (§1.4) |
| Random access (jump to page 5) | Trivial | Not supported — sequential only |
| Total count | Free (same `WHERE`) | Still one `COUNT`, unchanged |
| Client state | `offset` integer | Opaque `cursor` string |

The sidebar only ever moves **forward** while scrolling, so the loss of random
access costs nothing.

---

## 5. Index strategy

### 5.1 Current indexes on `chat_session`

Verified against the running database:

```
"chat_session_pkey"          PRIMARY KEY, btree (id)
"ix_chat_session_class_id"   btree (class_id)
"ix_chat_session_is_pinned"  btree (is_pinned)
"ix_chat_session_user_id"    btree (user_id)
```

`ix_chat_session_user_id` narrows to one user, but the remaining work —
filtering `is_pinned`, sorting by `updated_at`, breaking ties by `id` — is done
with a sort on top of that scan.

### 5.2 New composite indexes

```sql
CREATE INDEX ix_chat_session_user_pinned_updated
    ON chat_session (user_id, is_pinned, updated_at, id);

CREATE INDEX ix_chat_session_user_pinned_pinned_at
    ON chat_session (user_id, is_pinned, pinned_at, id);
```

Column order is deliberate:

1. `user_id` — equality predicate, always present (RLS).
2. `is_pinned` — equality predicate, always present in cursor mode.
3. the sort column — the index is read in its natural order, so no sort node.
4. `id` — the tiebreaker, so a tie is resolved inside the index.

With this order the planner can satisfy `WHERE user_id = ? AND is_pinned = ?`
plus `ORDER BY <ts>, id` by walking the index, and the keyset predicate becomes
a range start instead of a filter.

### 5.3 Why not one index

`recent` sorts by `updated_at` and `pinned` sorts by `pinned_at`. A single index
can only be in natural order for one of them. Two indexes cost a little write
amplification on `chat_session` (which is written once per chat turn) and buy a
sort-free read for both blocks.

### 5.4 Migration

`alembic/versions/0055_chat_cursor_pagination.py`, `down_revision =
"0054_seed_comprehensive_skill_bank"` (the head at the time of writing). Both
`create_index` calls are portable to SQLite, so the test fixture builds them too.

---

## 6. Sequence

```
Frontend (sidebar mount)
  │
  ├─ GET /api/history?class_id=X&section=pinned&limit=50
  │     └─ get_sessions_cursor(section="pinned", cursor=None)
  │          ├─ COUNT(*) WHERE user_id AND is_pinned=true  → total
  │          ├─ SELECT ... ORDER BY pinned_at ASC, id ASC LIMIT 51
  │          └─ next_cursor = encode(last row) if 51 rows
  │
  └─ GET /api/history?class_id=X&section=recent&limit=20
        └─ get_sessions_cursor(section="recent", cursor=None)
             ├─ COUNT(*) WHERE user_id AND is_pinned=false → total
             ├─ SELECT ... ORDER BY updated_at DESC, id DESC LIMIT 21
             └─ next_cursor = encode(last row) if 21 rows

Frontend (student scrolls to the end of the Recent block)
  │
  └─ GET /api/history?class_id=X&section=recent&cursor=<next_cursor>&limit=20
        └─ get_sessions_cursor(section="recent", cursor=<opaque>)
             ├─ decode_cursor(cursor, "recent") → (t, id)
             ├─ COUNT(*) ... → total (unchanged)
             ├─ SELECT ... WHERE (updated_at,id) < (t,id) ORDER BY ... LIMIT 21
             └─ next_cursor = encode(last row) or null
```

---

## 7. Backward compatibility

| Concern | Guarantee |
|---|---|
| Existing frontend calls `GET /api/history?class_id=...` | `section` is absent → the router runs the **untouched** `get_sessions_by_class()`; same rows, same order, same `total` |
| Existing response consumers | `next_cursor` is a new field with default `null`; nothing is removed or renamed |
| `GET /api/history/search` | Not touched — still `limit`/`offset` |
| `GET /api/history/{session_id}` | Not touched — still returns the full transcript |
| `sortSessionsWithPinned()` on the client | Kept; each page already arrives in the right order, so re-sorting is a no-op |
| Database | Only two indexes are added; no column, constraint or data change |

`ChatSessionListResponse` gains one optional field:

```python
class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionResponse] = Field(default_factory=list)
    total: int = 0
    # AI-185: opaque keyset cursor for the next page; null on the last page
    # and always null for the legacy offset mode.
    next_cursor: str | None = None
```

---

## 8. Benchmark (AC-07)

Measured with `scripts/benchmark_history_pagination.py` against the local
PostgreSQL instance, 20 iterations per scenario after 3 warm-up runs. The script
seeds one throwaway user and class, spreads `updated_at` evenly, and deletes the
rows afterwards.

### 8.1 At 5,000 sessions (the size the plan targets)

| Scenario | Rows returned | Median | p95 |
|---|---:|---:|---:|
| `OFFSET 0`, `limit 20` | 20 | 9.42 ms | 15.38 ms |
| `OFFSET 4980`, `limit 20` | 20 | 12.65 ms | 13.59 ms |
| Cursor, last page | 20 | 7.44 ms | 8.32 ms |

### 8.2 At 50,000 sessions (scale check)

| Scenario | Rows returned | Median | p95 |
|---|---:|---:|---:|
| `OFFSET 0`, `limit 20` | 20 | 46.13 ms | 47.95 ms |
| `OFFSET 49980`, `limit 20` | 20 | 105.08 ms | 122.40 ms |
| Cursor, last page | 20 | 13.48 ms | 14.00 ms |

At 50,000 rows the deep `OFFSET` page is **7.8× slower** than the equivalent
cursor page (105.08 ms vs 13.48 ms), and 10× the 5,000-row deep-offset cost —
the linear growth the design predicted. The cursor page barely moves (7.44 ms →
13.48 ms), which is the flat curve AC-07 asks for.

Both modes were verified to return **the same page** at the same depth
(`offset deep page == cursor last page: True`, identical first id), so the
comparison is like-for-like rather than two different result sets.

### 8.3 Why: the query plans

`EXPLAIN (ANALYZE, BUFFERS)` on the 5,000-row dataset:

```
-- OFFSET 4980
Limit  (actual time=8.932..8.936 rows=20)
  ->  Sort  (Sort Key: is_pinned DESC, pinned_at, updated_at DESC, created_at DESC)
             (Sort Method: quicksort  Memory: 544kB  rows=5000)
        ->  Seq Scan on chat_session  (rows=5000)
Buffers: shared hit=86    Execution Time: 9.350 ms

-- Cursor, last page
Limit  (actual time=0.124..0.132 rows=21)
  ->  Index Scan Backward using ix_chat_session_user_pinned_updated
        Index Cond: (user_id = ? AND is_pinned = false)
Buffers: shared hit=5     Execution Time: 0.207 ms
```

The offset path sorts all 5,000 rows before discarding 4,980 of them. The cursor
path seeks the index and stops after 21 rows — no `Sort` node at all.

### 8.4 A side benefit worth noting

The legacy `OFFSET` query sorts on four columns
(`is_pinned DESC, pinned_at ASC NULLS LAST, updated_at DESC, created_at DESC`),
which no single index can satisfy, so even `OFFSET 0` pays for a full sort
(46 ms at 50,000 rows). Splitting the sidebar into two sections means each
cursor query sorts on only two columns, which is exactly what the composite
indexes in §5 cover. The first page gets faster too, not just the deep pages.

### 8.5 Reproducing

```bash
# from the backend root, with DATABASE_URL pointing at a migrated database
python scripts/benchmark_history_pagination.py --rows 5000
python scripts/benchmark_history_pagination.py --rows 50000
```

`--keep` leaves the seeded rows in place for inspection; `--runs` and
`--warmup` control the sampling.

---

## 9. Files

### Backend (`course-qa-agent-be`)

| File | Change |
|---|---|
| `docs/design/ai-185-cursor-pagination.md` | new — this document (Design branch) |
| `app/services/pagination.py` | new — `encode_cursor`, `decode_cursor`, `InvalidCursorError` |
| `app/services/history_service.py` | add `get_sessions_cursor()`; `get_sessions_by_class()` untouched |
| `app/schemas/history.py` | add `next_cursor` to `ChatSessionListResponse` |
| `app/routers/history/router.py` | add `section` + `cursor` query params and the mode switch |
| `alembic/versions/0055_chat_cursor_pagination.py` | new — two composite indexes |
| `tests/migrations/test_syllabus_handover_migration_graph.py` | bump `HEAD_REVISION` |
| `tests/test_history.py` | 12 new cursor tests |
| `scripts/benchmark_history_pagination.py` | new — AC-07 measurement |

### Frontend (`course-qa-agent-fe`)

| File | Change |
|---|---|
| `features/history/types.ts` | `ChatHistorySection`, `next_cursor`, `ChatSessionPageQuery` |
| `features/history/api.ts` | `getSessionsPage()` |
| `features/history/merge-sessions.ts` | new — `mergeSessionPages()` |
| `features/history/merge-sessions.test.ts` | new |
| `features/history/cursor-api.test.ts` | new |
| `features/history/chat-history-sidebar.tsx` | two cursors, "Load more", badge from `total` |
