# AI-158 — Teacher absence and ticket handover (auto + manual)

> **Ticket:** [AI-158](https://ai03.atlassian.net/browse/AI-158) (Epic AI-145: Class Schedule & Attendance) | **Priority:** High | **Story Points:** 13 SP
> **Sprint:** Sprint 4 — Quiz & Attendance (2026-11-01 → 2026-11-13)
> **Assignee:** Bui Trong Suu
> **Status:** Design (not implemented)
> **Target branch:** `features/Implementation_TeacherAbsenceHandover`
> **Design doc:** `docs/design/ai-158-teacher-absence-handover.md` (this file)
> **Related:** AI-81 (student ticket API), AI-83 (trainer inbox, class-scoped), AI-87 (in-app reply notification), AI-89 (ticket lifecycle), AI-136 (attendance API), AI-137 (escalation), AI-155 (attendance/handover schema), AI-156 (holiday service), AI-140 (leave requests).

This document is the design contract for AI-158. Every claim about existing code was
verified against the repository on 2026-11-09, on branch
`features/Implementation_TeacherAbsenceHandover`.

### Mapping to the planning document (`ke_hoach_task_AI-158.md`, step 0.3)

| Required section | Where |
|---|---|
| Data model | §3 |
| Endpoints + permission matrix | §4.1, §4.2 |
| Business flows | §5 |
| State machine + invariants | §6 |
| Error matrix | §4.5 |
| Decisions D1–D16 | §2 |

---

## 1. Purpose and scope

A trainer marks their **day status** (`present` / `off`). When a trainer is off:

- Open tickets of that trainer are **transferred** to another available trainer of the same
  class (least-open-tickets), or
- If **every** trainer of the class is off, the ticket **waits in the admin queue**.

A trainer who comes back **never reclaims** a transferred ticket.

A trainer can also request **planned leave** over a date range, naming a same-class
colleague. The recipient accepts (tickets move for the whole range) or rejects (the
automatic flow runs instead). A **manual transfer outranks the automatic choice**.

Recipient, sender and student are notified, and the ticket keeps a history of **who moved
it, when and why**.

### 1.1 Acceptance criteria (Jira AI-158)

| AC | Requirement | How this design satisfies it |
|---|---|---|
| **AC-01** | Teacher/Admin marks daily status present/off | `trainer_day_status` table + `PUT /api/trainer-status` |
| **AC-02** | Teacher off → OPEN tickets and newly assigned tickets move to an available same-class teacher (round-robin or least-open-tickets) | `handover_service.sweep_for_trainer()` picks **least-open-tickets**, runs lazily on mark-off / ticket create / ticket read |
| **AC-03** | If every teacher of the class is off → the ticket waits in the admin queue | `ticket.queued_for_admin_at` + `GET /api/admin/tickets/queue` |
| **AC-04** | A returning teacher must not reclaim transferred tickets | No "reclaim" endpoint; the sweep never sets an owner back to a returning `present` trainer |
| **AC-05** | Teacher schedules leave and picks a same-class teacher; recipient accepts/rejects; accept transfers within the range; reject triggers auto; manual outranks auto | `leave_request` (minimal) + `ticket_handover(reason='manual_transfer')` + accept/reject endpoints |
| **AC-06** | Recipient, sender and student are notified; history records who/when/why | System `TicketReply` (reuses AI-87 unread) + `ticket_handover` row + handover fields on the ticket DTO |

### 1.2 In scope

`trainer_day_status`; automatic transfer by least-open-tickets; admin queue; no-reclaim;
planned leave with accept/reject; notifications and handover history; admin queue view and
direct admin replies; guards (holidays, 7-day expiry, escalation SLA).

### 1.3 Out of scope

Cross-class emergency assignment; stateful round-robin; a dedicated `notification` table or
email/push; a new ticket status (`QUEUED_ADMIN`); automatic return when a trainer becomes
present; half-day or per-hour leave; session-level substitute teaching; broad ticket/admin
UI refactors.

### 1.4 Design principles

1. **No new ticket status.** `OPEN / ANSWERED / RESOLVED / EXPIRED` stays as shipped in AI-81/AI-89.
2. **Inbox visibility is unchanged.** Trainer lists stay class-scoped (AI-83); no regression.
3. **`owner_trainer_id` means "who is responsible"**, not "the only person who can see it".
4. **No cron, no queue service.** Sweeps are lazy, exactly like `escalate_stale_tickets()`.

---

## 2. Decisions

### 2.1 D1–D16 (chốt)

| # | Decision | Choice | Note |
|---|---|---|---|
| **D1** | Add `ticket.owner_trainer_id` (NULL, FK user) | ✅ | Backfill = `class.trainer_id`; owner = responsible trainer |
| **D2** | Add `ticket.queued_for_admin_at` (NULL, timestamptz) | ✅ | NULL = not queued |
| **D3** | `trainer_day_status` is the **single source** of availability | ✅ | UNIQUE(trainer_id, date); status ∈ {present, off} |
| **D4** | No new ticket status | ✅ | Avoids touching CHECKs, expiry, counts, reopen |
| **D5** | Inbox stays class-scoped | ✅ | No AI-83 regression; owner is for display/routing only |
| **D6** | Replacement is chosen by **least-open-tickets** | ✅ | `COUNT(ticket) WHERE owner=? AND status='OPEN'`; tie-break `user.id` |
| **D7** | Sweeps are **lazy**, no cron | ✅ | Mark status, `POST /api/tickets`, `GET /api/tickets*` |
| **D8** | Notify via a **system `TicketReply`** | ✅ | Student unread via AI-87; trainers see it in the thread |
| **D9** | Single-trainer class going off → **queue**, owner unchanged | ✅ | Returning trainer handles it; no reclaim needed |
| **D10** | Queued tickets **pause the 7-day expiry** | ✅ | No dead tickets in the queue |
| **D11** | Escalation **skips** queued tickets | ✅ | Avoids assigning a co-trainer who is also off |
| **D12** | Call `ensure_working_day()` before creating a handover | ✅ | Satisfies AI-156 AC-04 |
| **D13** | AC-05 leave: **reuse AI-140's table if it exists, otherwise AI-158 ships the minimal one** | ✅ **resolved: AI-158 ships it** | Verified: no `leave_request` / `LeaveRequest` anywhere in `app/`. AI-140 will reuse this table |
| **D14** | ADMIN may **reply** (PA1); cross-class assign is a later phase | ✅ | PA1 is required for the queue to be useful |
| **D15** | New migration — **`0046_absence_handover`**, `down_revision='0040_quiz_validation'` | ✅ **corrected** | See §2.2 |
| **D16** | No change to existing ticket formulas/fields | ✅ | Nullable additions only |

### 2.2 Deviations from the planning document

Both deviations were found by reading `alembic/versions/` directly; the plan was written
before AI-149…AI-160 migrations landed.

| Plan says | Reality (verified) | Corrected in this design |
|---|---|---|
| New revision id `0041_absence_handover` | Revision ids `0041` are **already used twice**: `0041_merge_quiz_heads`, `0041_skill_taxonomy` | Use **`0046_absence_handover`** |
| `down_revision='0040_quiz_availability'` | `0040_quiz_availability` is **not** the head. Chain tail: `0044_merge_qbank_quiz_heads` → `0045_quiz_show_solutions` → `0040_quiz_validation` (nothing references `0040_quiz_validation`, so it is the single head) | `down_revision = "0040_quiz_validation"` |
| Step 0.5 expects 1 head `0040_quiz_availability` | `alembic heads` will report `0040_quiz_validation` | Phase 0.5 must be re-baselined; **this doc, not the plan, is authoritative** |
| Backfill with `UPDATE ticket t ... FROM class c` | `UPDATE ... FROM` is not portable to the SQLite test fixture | Use a correlated subquery (§3.5) |

> The revision id `0040_quiz_validation` is confusingly numbered (it was created last), but
> it is the real head. `0046_absence_handover` is 21 characters, inside the 32-character cap
> enforced by `tests/test_alembic_revision_ids.py`.

---

## 3. Data model and migration

### 3.1 Schema overview

```text
ticket (extended)
  + owner_trainer_id      UUID FK user.id ON DELETE SET NULL   NULL  INDEX
  + queued_for_admin_at   TIMESTAMPTZ                          NULL  INDEX

trainer_day_status (new)
  id            UUID PK
  trainer_id    UUID FK user.id ON DELETE CASCADE
  date          DATE NOT NULL
  status        VARCHAR(20) NOT NULL      -- present | off
  note          TEXT NULL
  recorded_by   UUID FK user.id ON DELETE SET NULL
  created_at / updated_at TIMESTAMPTZ
  CHECK (status IN ('present','off'))
  UNIQUE (trainer_id, date)
  INDEX (date, status)

leave_request (new — AI-158 ships it, see D13)
  id                 UUID PK
  trainer_id         UUID FK user.id ON DELETE CASCADE
  date_from          DATE NOT NULL
  date_to            DATE NOT NULL
  target_trainer_id  UUID FK user.id ON DELETE RESTRICT
  reason             TEXT NULL
  status             VARCHAR(20) NOT NULL DEFAULT 'pending'  -- pending|accepted|rejected
  responded_by       UUID FK user.id ON DELETE SET NULL
  responded_at       TIMESTAMPTZ NULL
  created_at         TIMESTAMPTZ
  CHECK (date_to >= date_from)
  CHECK (status IN ('pending','accepted','rejected'))
  CHECK (trainer_id <> target_trainer_id)
  INDEX (trainer_id, status)

ticket_handover (shipped by AI-155 — structure UNCHANGED)
  ticket_id, from_trainer_id, to_trainer_id,
  reason ∈ {auto_absent, manual_transfer},
  status ∈ {pending, accepted, rejected},
  created_at, responded_at
  UNIQUE(ticket_id) WHERE status='pending'
  INDEX (ticket_id), INDEX (to_trainer_id, status)
```

`ticket_handover` already enforces everything AI-158 needs (`app/models/attendance.py`):
`ck_ticket_handover_same_trainer`, `ck_ticket_handover_reason`, `ck_ticket_handover_status`,
`ix_ticket_handover_ticket`, `uq_ticket_handover_pending` (partial on `status='pending'`),
`ix_ticket_handover_to_status`. **Do not change this table.**

### 3.2 `app/models/ticket.py`

```python
owner_trainer_id: Mapped[uuid.UUID | None] = mapped_column(
    Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
)
queued_for_admin_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True, index=True
)
# Joined so an inbox page does not issue one SELECT per ticket.
owner: Mapped[Optional["User"]] = relationship(
    "User", foreign_keys=[owner_trainer_id], lazy="joined"
)

@property
def owner_trainer_name(self) -> str | None:
    return self.owner.full_name if self.owner is not None else None
```

> ⚠️ `Ticket` will hold **three** FKs to `user` (`student_id`, `escalated_to_id`,
> `owner_trainer_id`). Declaring `foreign_keys=` on the relationship is **mandatory** —
> `escalated_to` already does it for the same reason. Without it SQLAlchemy raises an
> ambiguous-join error at import time.

### 3.3 `app/models/attendance.py`

Add next to the existing constants (`ATTENDANCE_STATUSES`, `HANDOVER_REASONS`, …):

```python
TRAINER_DAY_STATUSES = ("present", "off")
LEAVE_REQUEST_STATUSES = ("pending", "accepted", "rejected")
```

`TrainerDayStatus` and `LeaveRequest` follow the file's existing style: `String(20)` +
`CheckConstraint` (not native PG enums, per AI-155 D6), `TIMESTAMPTZ` timestamps with
`server_default=func.now()`, and both `postgresql_where` and `sqlite_where` on any partial
index. `TrainerDayStatus` uses `UniqueConstraint("trainer_id", "date")` — a plain unique
constraint, not a partial index.

Export both from `app/models/__init__.py` so `Base.metadata` registers them for the SQLite
test fixture.

### 3.4 Migration `0046_absence_handover`

```python
revision = "0046_absence_handover"
down_revision = "0040_quiz_validation"
```

`upgrade()` — in this order:

| Step | Detail |
|---|---|
| 1 | `batch_alter_table("ticket")`: add `owner_trainer_id`, `queued_for_admin_at`, FK `ON DELETE SET NULL`, `create_index("ix_ticket_owner_trainer_id")`, `create_index("ix_ticket_queued_for_admin_at")` |
| 2 | Backfill (see §3.5) |
| 3 | `create_table("trainer_day_status")` + CHECK + UNIQUE + index `(date, status)` |
| 4 | `create_table("leave_request")` + 3 CHECKs + index `(trainer_id, status)` |

`downgrade()` — reverse order: drop `leave_request`, drop `trainer_day_status`, drop the two
indexes, then `batch_alter_table("ticket")` dropping both columns.

**Idempotency** (same style as `0028_attendance_schema.py`): guard every step with
`sa.inspect(bind).get_table_names()` / `get_columns("ticket")`, so a partially applied
migration can be re-run without error.

### 3.5 Backfill — portable form

The plan's `UPDATE ticket t ... FROM class c` is PostgreSQL-only (SQLite gained
`UPDATE … FROM` in 3.33 and the test fixture does not rely on it). Use a correlated
subquery, which runs on both engines:

```sql
UPDATE ticket
SET owner_trainer_id = (
    SELECT c.trainer_id FROM "class" c WHERE c.id = ticket.class_id
)
WHERE owner_trainer_id IS NULL
```

`class` is quoted because it is a keyword in several dialects. `Class.trainer_id` is the
primary trainer column (confirmed in `app/services/course_service.py`).

Verification after migrate: `SELECT COUNT(*) FROM ticket WHERE owner_trainer_id IS NULL`
must be `0` — every class has a primary trainer, so no ticket can stay unowned.

> **New tickets need the same rule in code.** A migration only backfills existing rows.
> `create_student_ticket()` must therefore set `owner_trainer_id = clazz.trainer_id`
> explicitly; otherwise every new ticket starts with a NULL owner and breaks invariant I3.

---

## 4. API contract

`Authorization: Bearer <JWT>`, JSON snake_case, errors `{"detail": "..."}`.

### 4.1 Endpoints

| # | Method | Path | Role | Purpose |
|---|---|---|---|---|
| 1 | `GET` | `/api/trainer-status?date=` | TRAINER (self), ADMIN | Read a day status |
| 2 | `PUT` | `/api/trainer-status` | TRAINER (self), ADMIN (any trainer) | Set present/off for a day |
| 3 | `GET` | `/api/classes/{class_id}/trainer-status?date=` | ADMIN, class staff | Day status of the class trainers |
| 4 | `GET` | `/api/tickets` (extended) | TRAINER, **ADMIN** | Inbox; adds owner/queued/handover fields |
| 5 | `POST` | `/api/tickets/{id}/replies` (extended) | STUDENT, TRAINER, **ADMIN** | Admin replies directly |
| 6 | `GET` | `/api/admin/tickets/queue` | ADMIN | Tickets waiting for an admin |
| 7 | `POST` | `/api/tickets/{id}/handover` | ADMIN | Manual assign to a trainer |
| 8 | `GET` | `/api/handovers/mine` | TRAINER | Handovers awaiting my answer |
| 9 | `POST` | `/api/handovers/{id}/accept` | TRAINER (recipient) | Accept the ticket |
| 10 | `POST` | `/api/handovers/{id}/reject` | TRAINER (recipient) | Reject → automatic flow |
| 11 | `POST` | `/api/leave-requests` | TRAINER | Create a planned leave |
| 12 | `GET` | `/api/leave-requests/mine` | TRAINER | Leaves I sent / received |
| 13 | `POST` | `/api/leave-requests/{id}/accept` | TRAINER (target) | Accept → transfer within the range |
| 14 | `POST` | `/api/leave-requests/{id}/reject` | TRAINER (target) | Reject → automatic flow |
| 15 | `GET` | `/api/admin/leave-requests` | ADMIN | (Optional) review leaves |

New routers: `app/routers/handover/` (`trainer-status`, `handovers`, `leave-requests`,
`admin queue`), registered in `app/main.py` next to the attendance router.

### 4.2 Permission matrix

| Endpoint | ADMIN | Primary trainer | Co-trainer | Other-class recipient | Student | Outsider |
|---|---:|---:|---:|---:|---:|---:|
| 1–2 (self) | ✅ any | ✅ self | ✅ self | ❌ 403 | ❌ 403 | ❌ 403 |
| 3 | ✅ | ✅ own class | ✅ own class | ❌ 403 | ❌ 403 | ❌ 403 |
| 4 inbox | ✅ queue only | ✅ | ✅ | ❌ | ❌ | ❌ |
| 5 reply | ✅ | ✅ own class | ✅ own class | ✅ if current owner | ✅ own ticket | ❌ 403 |
| 6 queue | ✅ | ❌ 403 | ❌ 403 | ❌ | ❌ | ❌ |
| 7 assign | ✅ | ❌ 403 | ❌ 403 | ❌ | ❌ | ❌ |
| 8–10 handover | ❌ 403 | ✅ if `to_trainer_id` | ✅ if `to_trainer_id` | ✅ if `to_trainer_id` | ❌ | ❌ |
| 11–14 leave | ✅ optional | ✅ self | ✅ self | ✅ if target | ❌ | ❌ |

**Visibility rule:** a trainer sees a ticket when it belongs to one of their classes
(AI-83, primary ∪ co-trainer via `class_ids_for_trainer(active_only=True)`) **or** they are
`owner_trainer_id` **or** they are `to_trainer_id` of a pending handover. **ADMIN** sees only
`queued_for_admin_at IS NOT NULL` tickets in endpoint 4. No access is widened for outsiders.

### 4.3 DTOs

`TicketRead` — additive only, no existing field changes:

```json
{
  "owner_trainer_id": "uuid-or-null",
  "owner_trainer_name": "Trainer A-or-null",
  "queued_for_admin_at": "2026-11-09T03:00:00Z-or-null",
  "handover_from_id": "uuid-or-null",
  "handover_from_name": "Trainer A-or-null",
  "handover_reason": "auto_absent | manual_transfer | null",
  "handover_at": "2026-11-09T03:00:00Z-or-null"
}
```

`handover_*` describe the **most recent accepted** handover; `null` if the ticket was never
transferred. `TicketThreadRead` and `TicketInboxItem` inherit all of them.

`TrainerDayStatusRead`:

```json
{ "trainer_id": "uuid", "trainer_name": "Trainer A", "date": "2026-11-09",
  "status": "present|off", "note": null,
  "recorded_by": "uuid-or-null", "updated_at": "2026-11-09T02:00:00Z" }
```

`HandoverRead`:

```json
{ "id": "uuid", "ticket_id": "uuid", "ticket_question": "...",
  "from_trainer_id": "uuid", "from_trainer_name": "A",
  "to_trainer_id": "uuid", "to_trainer_name": "B",
  "reason": "auto_absent", "status": "pending",
  "created_at": "...", "responded_at": null }
```

`LeaveRequestCreate` / `LeaveRequestRead`:

```json
{ "date_from": "2026-11-10", "date_to": "2026-11-12",
  "target_trainer_id": "uuid", "reason": "Family trip" }
```

`LeaveRequestRead` adds `id`, `trainer_id`, `trainer_name`, `target_trainer_name`,
`status`, `responded_by`, `responded_at`, `created_at`.

`AdminQueueItem` = `TicketInboxItem` + `{ "absent_trainers": ["A"], "queued_for_admin_at": "..." }`.
It carries `replies` (inherited), so an admin can read the whole thread without calling
`GET /api/tickets/{id}` — which stays student-only (§7.2).

### 4.4 Error matrix

| Case | Status | Detail |
|---|---|---|
| Mark a day older than 7 days | `400` | "Only the last 7 days can be marked." |
| `status` outside {present, off} | `422` | Pydantic |
| Trainer sets another trainer's status | `403` | "Only admins can change another trainer's status." |
| Unknown class | `404` | "Class not found." |
| Trainer not in the class views status | `403` | "Only this class' teachers can view trainer status." |
| Non-admin calls the admin queue | `403` | "Only admins can view the admin queue." |
| Hand over a `RESOLVED`/`EXPIRED` ticket | `409` | "Only open or answered tickets can be handed over." |
| Assign to the current owner | `409` | "Ticket already belongs to this trainer." |
| Cross-class assign (this phase) | `400` | "Target trainer does not teach this class." |
| Handover not mine | `403` | "This handover is not assigned to you." |
| Handover already answered | `409` | "This handover was already answered." |
| Leave `date_from > date_to` | `422` | Pydantic |
| Leave target not in the class | `400` | "Target trainer does not teach this class." |
| Leave target is self | `400` | "You cannot delegate to yourself." |
| Accept an answered leave | `409` | "This leave request was already answered." |
| Admin replies to a `RESOLVED` ticket | `409` | "Only open tickets can be answered." |

> Endpoint 3 reuses `require_class_staff()` (`app/routers/attendance/permissions.py`), which
> raises `403 "Only this class' teachers can manage attendance."` rather than the wording
> above. We accept that message instead of duplicating the authorization check — one code
> path, no chance of the two checks drifting apart.

---

## 5. Business flows

### 5.1 AC-01 — Marking a day status

```text
Trainer/Admin
  └─ PUT /api/trainer-status { date?, status: present|off, trainer_id? (admin only) }
       ├─ validate: date within [today-7, today]; trainer_id only from ADMIN
       ├─ upsert trainer_day_status(trainer_id, date)
       ├─ status = off     → handover_service.sweep_for_trainer(trainer_id, date)
       └─ status = present → handover_service.clear_queue_for(trainer_id, date)
```

`date` defaults to today (`local_date()` from `holiday_service`). Repeating the same call is
idempotent: the unique constraint makes the second call an update, and the sweep transfers
nothing because `owner` no longer matches the absent trainer.

### 5.2 AC-02 / AC-03 — Automatic transfer and the admin queue

```text
sweep_for_trainer(db, trainer_id, day) -> int   # how many tickets were moved or queued
  1. classes = class_ids_for_trainer(db, trainer_id, active_only=True)   # primary ∪ co
  2. for each class: sweep_class(db, class_id, day)

sweep_class(db, class_id, day) -> int
  1. absent = {trainer_id of this class with trainer_day_status(status='off', date=day)}
  2. if absent is empty: return 0                     # one indexed query, cheap on every read
  3. for trainer_id in absent:
       ensure_working_day(db, day, class_id)          # HolidayBlocked → skip this class
       tickets = Ticket(status='OPEN', owner_trainer_id=trainer_id, class_id=class_id)
       candidates = available_trainers(db, class_id, day) - {trainer_id}
       for ticket in tickets:
            if candidates:
                to = pick_replacement(db, class_id, day, exclude={trainer_id})
                assign(db, ticket, to, reason='auto_absent', status='accepted', actor=...)
            else:
                queue_for_admin(db, ticket)
```

`available_trainers(class_id, day)` = `{class.trainer_id} ∪ class_trainer.trainer_id` minus
anyone whose `trainer_day_status.status = 'off'` on `day`. Archived classes are excluded,
matching the inbox (`active_only=True`).

`pick_replacement` ordering:

1. An **accepted** `leave_request` covering `day` whose `target_trainer_id` is in
   `available_trainers` → return that target first (manual outranks auto, AC-05).
2. Otherwise the candidate with the fewest `OPEN` tickets it owns, tie-broken by `user.id`
   for determinism (D6).

No candidate exists ⇒ `queue_for_admin`: `queued_for_admin_at = now()`, **owner unchanged**
(D9). The ticket keeps its owner so the returning trainer can answer it directly (AC-04).

### 5.3 AC-04 — Trainer returns

```text
PUT /api/trainer-status { status: present }
  └─ clear_queue_for(db, trainer_id, day):
        UPDATE ticket SET queued_for_admin_at = NULL
        WHERE owner_trainer_id = trainer_id AND queued_for_admin_at IS NOT NULL
     (tickets owned by anyone else are untouched → no reclaim)
```

`clear_queue_for` never changes `owner_trainer_id`, so a returning trainer cannot pull back a
ticket that was transferred away while they were off.

### 5.4 AC-05 — Planned leave

```text
Trainer A creates leave_request(A, [d1..d2], target=B) → status='pending'
  └─ B is notified: system TicketReply on the affected tickets + /api/handovers/mine

B accepts (POST /api/leave-requests/{id}/accept):
  1. upsert trainer_day_status(A, 'off') for every day in [d1..d2]      # invariant I7
  2. for each day: sweep_for_trainer(A, day)                            # prefers target B
  3. leave_request.status='accepted', responded_by=B, responded_at=now

B rejects (POST /api/leave-requests/{id}/reject):
  1. leave_request.status='rejected', responded_by=B, responded_at=now
  2. sweep_for_trainer(A, today)  → normal least-open flow
```

Validation on create: target is a trainer of at least one class A teaches; target ≠ A;
`date_from <= date_to`; the range does not start more than 7 days in the past. Accept/reject
requires the caller to be `target_trainer_id`; a second answer returns `409`.

### 5.5 AC-06 — Notifications and history

```text
assign(db, ticket, to, reason, actor_id, status='accepted'):
  1. close any older pending handover → status='rejected', responded_at=now   # invariant I1
  2. create TicketHandover(ticket_id, from=ticket.owner_trainer_id, to, reason, status)
  3. ticket.owner_trainer_id = to.id
  4. ticket.queued_for_admin_at = None
  5. db.add(TicketReply(
        ticket_id=ticket.id, user_id=actor_id,
        message=f"Ticket transferred from {from_name} to {to.full_name} ({reason})."
     ))
  6. commit
```

- **Student** sees an unread badge because `TicketReply.user_id != student_id` and
  `student_seen_at` is older (AI-87). No notification table is needed.
- **Recipient** sees the ticket with `owner_trainer_name = self`, plus `/api/handovers/mine`.
- **Sender** sees it in the ticket thread and in the handover row.
- **History (AC-06):** `ticket_handover` (from, to, reason, created_at, responded_at) plus
  the system replies. Nothing is deleted; rejected/accepted rows stay queryable.

**System reply wording** (Phase 6.1):

| Event | Message |
|---|---|
| Transfer | `Ticket transferred from {from} to {to} ({reason}).` |
| Reject | `Handover from {from} was rejected; the ticket returns to the automatic queue.` |
| Queue | `All trainers are off today; the ticket is waiting for an administrator.` |
| Admin reply | the admin's own text (no system message) |

**Who authors the system reply:** the acting user — the trainer marking themselves off, the
admin assigning, the recipient accepting. For a **lazy** sweep triggered by a read (where no
one acted on this ticket), author it as `from_trainer_id` so a random reader's name never
appears in the thread.

### 5.6 Mandatory guards

| Guard | Location | Behaviour |
|---|---|---|
| Expiry | `ticket_service.expire_open_tickets` | Add `Ticket.queued_for_admin_at.is_(None)` |
| Escalation | `ticket_service.escalate_stale_tickets` | Add `Ticket.queued_for_admin_at.is_(None)` to the query filters |
| Holiday | `handover_service.sweep_*` | `ensure_working_day()`; catch `HolidayBlocked` → skip the class |
| Idempotency | `sweep_*` | Only act when `ticket.owner_trainer_id` is still the absent trainer |
| Concurrency | `assign()` | Wrap in a transaction; on `IntegrityError` from `uq_ticket_handover_pending`, roll back and retry once |
| Already-resolved | `assign()` | Skip tickets whose status is not `OPEN` |

---

## 6. State machine and invariants

```text
Ticket.status:  OPEN ──► ANSWERED ──► RESOLVED
                  │                     │
                  ├──► EXPIRED          └──► OPEN (reopen)
                  └──► ANSWERED (trainer/admin reply)

TicketHandover.status: pending ──► accepted   (owner changes)
                              └──► rejected   (owner kept; auto flow re-runs)

Queue:  queued_for_admin_at != NULL  ⇔  owner is off and nobody can replace them
```

No new states are introduced (D4). `queued_for_admin_at` is an orthogonal marker on top of
`status='OPEN'`, which is why expiry, counts and reopen keep working untouched.

| # | Invariant |
|---|---|
| I1 | At most **one** `pending` `ticket_handover` per ticket |
| I2 | `ticket.owner_trainer_id` ∈ trainers of `ticket.class_id` (primary ∪ co-trainer) |
| I3 | `queued_for_admin_at IS NOT NULL` ⇒ `owner_trainer_id IS NOT NULL` |
| I4 | An `accepted` handover ⇒ `ticket.owner_trainer_id = to_trainer_id` |
| I5 | No ticket with `queued_for_admin_at != NULL` is `EXPIRED` |
| I6 | At most one `trainer_day_status` row per `(trainer_id, date)` |
| I7 | `leave_request.status='accepted'` ⇒ every day in the range has `trainer_day_status='off'` for that trainer |

I1 is enforced by the database (`uq_ticket_handover_pending`); I6 by
`UniqueConstraint(trainer_id, date)`. I2–I5 and I7 are enforced in the service layer and
asserted by `scripts/dev/ai158/check_invariants.py`.

---

## 7. Implementation notes against the current code

### 7.1 Hook points (verified)

| Where | File | Needed change |
|---|---|---|
| Ticket list | `ticket_service.list_trainer_tickets` | Admin branch returns queue only; call `sweep_class` for the returned scope |
| Ticket create | `ticket_service.create_student_ticket` | Set `owner_trainer_id = clazz.trainer_id`, then `sweep_class(clazz.id, today)` |
| Student ticket read | `ticket_service.get_student_ticket` | `sweep_class(ticket.class_id, today)` — cheap, returns early when nobody is off |
| Trainer reply | `ticket_service.add_trainer_reply` | Generalise to staff reply (ADMIN skips the class check) |
| Expiry | `ticket_service.expire_open_tickets` | Skip queued rows |
| Escalation | `ticket_service.escalate_stale_tickets` | Skip queued rows |
| Day status write | new `availability_service.set_day_status` | Trigger sweep / clear queue |

### 7.2 Gotchas that will bite during implementation

1. **`_inbox_items()` builds `TicketInboxItem` field by field.** It does *not* use
   `model_validate`, so adding fields to `TicketRead` is not enough — `_inbox_items()` must
   be updated or the new fields stay `null` in the inbox.
2. **`handover_from_name` cannot be a plain ORM property.** Unlike `owner`, there is no
   relationship returning a single "latest accepted handover". Compute it where the read
   model is built: a batched query over the page's ticket ids in `_inbox_items()`, and a
   transient attribute on the single-ticket paths (`create`/`resolve`/`reopen`), which
   `TicketRead.model_validate()` picks up via `from_attributes`.
3. **`GET /api/tickets/{ticket_id}` is student-only** (`_require_student`). Trainers read
   threads from `TicketInboxItem.replies`; admins read them from `AdminQueueItem.replies`.
   Do **not** widen that endpoint — no extra permission surface is needed for AC-06.
4. **`add_trainer_reply` only accepts `status == 'OPEN'`** and sets `ANSWERED`. Admin replies
   must reuse that rule, and additionally clear `queued_for_admin_at` (Phase 4.3).
5. **`_reopened_status()` counts every non-student reply as a trainer reply.** System
   handover messages therefore count too — desirable (the ticket did get attention), but it
   means reopening after a handover yields `ANSWERED`, not `OPEN`.
6. **`require_class_staff()` indexes on `active_only=True`.** Use the same flag in sweeps so
   an archived class never generates handovers.
7. **`HolidayBlocked(day, holiday)`** is raised, not returned. Catch it per class, not around
   the whole sweep, so one holiday does not abort the other classes.
8. **`TicketReply.user_id` is `ON DELETE RESTRICT`** — the author must be a real user, never a
   synthetic/system id. Use the acting user, or `from_trainer_id` for lazy sweeps.
9. **`class` is a keyword** in several dialects — always quote it in raw SQL.

### 7.3 Service surface to add

```python
# app/services/availability_service.py
get_day_status(db, trainer_id, day) -> str                 # default "present"
set_day_status(db, trainer_id, day, status, recorded_by, note=None) -> TrainerDayStatus
is_available(db, trainer_id, day) -> bool
available_trainers(db, class_id, day) -> list[User]

# app/services/handover_service.py
open_ticket_count(db, trainer_id) -> int
pick_replacement(db, class_id, day, exclude_ids) -> User | None
assign(db, ticket, to, reason, actor_id, status='accepted') -> TicketHandover
queue_for_admin(db, ticket, now=None) -> None
sweep_for_trainer(db, trainer_id, day) -> int
sweep_class(db, class_id, day) -> int
clear_queue_for(db, trainer_id, day) -> int

# app/services/leave_service.py
create_leave(db, trainer_id, date_from, date_to, target_trainer_id, reason) -> LeaveRequest
list_my_leaves(db, trainer_id) -> list[LeaveRequest]
respond_leave(db, leave_id, actor_id, accept: bool) -> LeaveRequest
```

`sweep_class` is the primitive; `sweep_for_trainer` is a thin wrapper over the trainer's
classes. A read path calls `sweep_class` directly, so reading one inbox never walks every
class in the system (the same reasoning as `escalate_stale_tickets(class_ids=...)`).

---

## 8. Test plan

| Layer | File | Covers |
|---|---|---|
| Schema | `tests/test_absence_schema.py` | tables, columns, UNIQUE, CHECKs, backfill result |
| Service | `tests/handover/test_availability_service.py` | default `present`, available trainers, upsert |
| Router | `tests/handover/test_trainer_status_router.py` | 200/403/404/422, admin acting on behalf, 7-day window |
| Service | `tests/handover/test_handover_service.py` | auto transfer, least-open, all-off → queue, no-reclaim, holiday skip, idempotency, single pending |
| Router | `tests/handover/test_admin_queue_router.py` | queue list, admin reply clears the queue, manual assign, 403s |
| Router | `tests/handover/test_leave_router.py`, `tests/handover/test_handover_respond.py` | leave accept/reject, handover accept/reject, I7 |
| Regression | `tests/tickets`, `tests/attendance` | no AI-81/83/89/136/137 regressions |

Negative tests (required, they prove the guards are load-bearing):

- Remove the `queued_for_admin_at IS NULL` filter from `expire_open_tickets` → the expiry test must FAIL.
- Remove it from `escalate_stale_tickets` → the escalation test must FAIL.
- Remove `ensure_working_day()` → the holiday test must FAIL.
- Skip the day-status upsert when accepting a leave → invariant I7 must FAIL.
- Insert two `trainer_day_status` rows for one `(trainer_id, date)` → `IntegrityError`.

---

## 9. Open questions

| # | Question | Impact | Default if unresolved |
|---|---|---|---|
| Q1 (D13) | Does AI-140 ship `leave_request` before AI-158? | Whether AI-158 adds the table | **Resolved:** no `leave_request` exists in `app/`; AI-158 ships the minimal table from §3.1 and AI-140 will reuse it |
| Q3 | Cross-class emergency assignment in this phase? | Scope of `POST /api/tickets/{id}/handover` | Same class only; cross-class deferred, returns `400` |
| Q5 | Should an admin be alerted before the queue? | Whether slicing needs a proactive notification | Queue only; no alerting in AI-158 |
