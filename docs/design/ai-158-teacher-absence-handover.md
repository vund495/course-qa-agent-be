# AI-158 — Teacher absence and ticket handover

> **Status:** implemented (BE Phase 1–6).
> **Related:** AI-81/AI-137 ticket lifecycle and escalation, AI-136 attendance,
> AI-155 attendance schema, AI-156 holiday service.

## 1. Scope

AI-158 adds the teacher availability and handover layer on top of the existing
student-ticket flow:

- A trainer can mark a day as `present` or `off`.
- When a trainer is `off`, their `OPEN` tickets are moved to an available
  colleague of the same class, or queued for an administrator when nobody else
  is available.
- A returning trainer does **not** reclaim tickets that were already handed
  over.
- An administrator can see the queue, reply directly, resolve tickets, and
  manually assign a ticket to another trainer of the same class.
- Trainers can request planned leave and select a colleague to cover the range.
  Accepting the request marks the requester `off` and prefers the chosen
  colleague for ticket handover.

## 2. Data model

`alembic/versions/0046_absence_handover.py` adds:

- `ticket.owner_trainer_id` (nullable FK to `user.id`, indexed) and
  `ticket.queued_for_admin_at` (nullable, indexed). Existing tickets are
  backfilled from `class.trainer_id`.
- `trainer_day_status`: one row per `(trainer_id, date)` with
  `status IN ('present', 'off')`.
- `leave_request`: trainer, inclusive date range, target trainer, reason,
  status (`pending` / `accepted` / `rejected`), responder and timestamps.

`ticket_handover` already existed in the AI-155 schema; AI-158 uses it for
auto, manual and pending handovers. A partial unique index keeps at most one
`pending` handover per ticket.

## 3. API

| Method | Path | Role | Purpose |
|---|---|---|---|
| `GET` | `/api/trainer-status?date=` | TRAINER, ADMIN | My day status |
| `PUT` | `/api/trainer-status` | TRAINER, ADMIN | Set `present` / `off` |
| `GET` | `/api/classes/{class_id}/trainer-status` | ADMIN, class staff | Class day status |
| `GET` | `/api/tickets` | TRAINER, ADMIN | Trainer inbox / admin queue view |
| `POST` | `/api/tickets/{id}/replies` | STUDENT, TRAINER, ADMIN | Reply; admin reply clears queue |
| `GET` | `/api/admin/tickets/queue` | ADMIN | Tickets waiting for admin |
| `POST` | `/api/tickets/{id}/handover` | ADMIN | Manual transfer in the same class |
| `GET` | `/api/handovers/mine` | TRAINER | Pending handovers addressed to me |
| `POST` | `/api/handovers/{id}/accept` | Recipient | Accept; become owner |
| `POST` | `/api/handovers/{id}/reject` | Recipient | Reject; run auto sweep |
| `POST` | `/api/leave-requests` | TRAINER | Create planned leave |
| `GET` | `/api/leave-requests/mine` | TRAINER | Sent and incoming requests |
| `POST` | `/api/leave-requests/{id}/accept` | Target | Mark `off` + transfer |
| `POST` | `/api/leave-requests/{id}/reject` | Target | Reject + auto sweep |

`TicketRead`, `TicketThreadRead` and `TicketInboxItem` now expose
`owner_trainer_id`, `owner_trainer_name`, `queued_for_admin_at`,
`handover_from_id`, `handover_from_name`, `handover_reason` and `handover_at`.
The handover fields describe the latest **accepted** handover.

## 4. Flow

### Day status

```text
PUT /api/trainer-status
  -> upsert trainer_day_status
  -> off: sweep_for_trainer(trainer, day)
  -> present: clear_queue_for(trainer, day)
```

`sweep_for_trainer` skips classes on holiday, skips tickets already queued, and
either assigns each open ticket to an available colleague or queues it for an
administrator. A returning trainer only clears the queue on tickets they still
own; transferred tickets stay with their new owner.

### Planned leave

```text
Trainer A creates leave [d1..d2] target B -> pending
B accepts:
  1. leave_request.status = accepted
  2. for each day: trainer_day_status(A, day) = off
     -> sweep_for_trainer(A, day) prefers B when B is available
B rejects:
  1. leave_request.status = rejected
  2. sweep_for_trainer(A, today, exclude B)
```

Manual coverage wins over least-open balancing only while the accepted leave
covers the day and B is available.

### Admin queue

Tickets enter the queue when `sweep_for_trainer` finds no available colleague.
Queue time does not count toward ticket expiration or escalation. An admin reply
sets the ticket to `ANSWERED` and clears `queued_for_admin_at`; a manual assign
sets the new owner and records a `manual_transfer` handover.

## 5. System replies

- Transfer: `Ticket transferred from {from} to {to} ({reason}).`
- Admin queue: `All trainers are off today; the ticket is waiting for an administrator.`
- Rejected handover: `Handover from {from} was rejected; the ticket returns to the automatic queue.`

## 6. Tests

- `tests/handover/test_handover_service.py` — core auto-handover, holiday guard,
  idempotency, least-open balancing, no reclaim, queue guards and concurrency.
- `tests/handover/test_availability_service.py` — day status and sweep wiring.
- `tests/handover/test_trainer_status_router.py` — trainer-status endpoints.
- `tests/handover/test_admin_queue_router.py` — admin queue, reply, assign.
- `tests/handover/test_leave_router.py` — leave create/accept/reject, manual
  priority, day-status invariant.
- `tests/handover/test_handover_respond.py` — pending handover accept/reject.
- `tests/tickets` — existing AI-81/AI-137 regression.

## 7. Notes and limits

- `leave_request` is the minimal AI-158 version; AI-140 must reuse it instead of
  creating a second leave table.
- Manual day-status changes are limited to today and the previous seven days;
  leave acceptance writes future `off` rows through the service layer.
- Admin manual assignment is same-class in this phase. Cross-class assignment is
  intentionally out of scope.
