# AI-157 - Student Weekly & Monthly Class Schedule

> **Ticket:** [AI-157](https://ai03.atlassian.net/browse/AI-157) (Epic AI-145: Class Schedule & Attendance) | **Priority:** High
> **Status:** Implemented
> **Target Branch:** `features/Implementation_StudentSchedule`
> **Depends on:** AI-136 (class sessions and student attendance), AI-155 (schedule schema), AI-156 (holiday service)
> **Related:** AI-158 (teacher absence and ticket handover)

---

## 1. Purpose

Give an enrolled student one read-only payload for both schedule views:

* the seven days of a selected week, including future sessions;
* the cells of a selected month, including holidays;
* the caller's own attendance status on past sessions;
* enough class metadata to know where to attend.

The screen itself lives in `course-qa-agent-fe`. This API deliberately does not
extend the staff `/api/classes/{class_id}/sessions` endpoint, because that
payload exposes attendance aggregates and is shared by teachers and admins.

### Acceptance criteria mapped to this contract

| AC | Where it is satisfied |
|---|---|
| AC-01 - week view shows days, subjects, times, attendance status, previous/next week, holiday labels | `GET /api/student/classes/{class_id}/schedule` returns dated sessions + holidays; the FE renders seven day columns with navigation. |
| AC-02 - month grid marks class days, shows holidays distinctly, opens day details | The same range endpoint returns every session and holiday in the month; the FE groups them into a Monday-first grid and a selected-day detail panel. |
| AC-03 - week/month toggle remembered | FE-only preference in `localStorage` (`student-class-schedule-view`). |
| AC-04 - both views usable on mobile | FE week view switches to a vertical day list below `md`; month cells stay a compact seven-column grid with a full-width day-detail panel. |

---

## 2. API contract

```http
GET /api/student/classes/{class_id}/schedule?from=2026-11-02&to=2026-11-08
Authorization: Bearer <student JWT>
```

* Caller must have an **ACTIVE enrollment** in the class. Admin and trainer
  tokens receive `403`, matching the existing student attendance endpoint.
* `from` / `to` use the shared `schedule_service.resolve_range` defaults and
  the 400-day maximum. A reversed range is `400`.
* The service materialises missing `class_session` rows for the whole requested
  range, including future dates.
* Sessions are ordered by `start_at`, then `id`.
* Holidays are ordered by date.
* Only the caller's attendance row is read; other students' statuses and notes
  can never appear in the response.

### Response

```json
{
  "class_id": "9c1a...",
  "class_code": "CS101-FA26-001",
  "class_name": "Computer Science 101",
  "date_from": "2026-11-02",
  "date_to": "2026-11-08",
  "today": "2026-11-05",
  "meeting_url": "https://meet.example.com/class",
  "sessions": [
    {
      "id": "aa11...",
      "date": "2026-11-02",
      "start_at": "2026-11-02T19:00:00+07:00",
      "end_at": "2026-11-02T21:00:00+07:00",
      "subject": "Computer Science 101",
      "trainer_name": "Academic Trainer",
      "status": "scheduled",
      "attendance_status": "present",
      "attendance_note": null
    }
  ],
  "holidays": [
    {
      "date": "2026-11-04",
      "name": "Class holiday",
      "type": "admin",
      "scope": "class"
    }
  ]
}
```

`today` is the Vietnam-local date on the server. The FE uses it to distinguish
an **upcoming** session from a past **unmarked** session without trusting the
browser clock.

`meeting_url` comes from the class information page and may be `null`.

---

## 3. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Dedicated student schedule DTO instead of reusing `ClassSessionRead` | `ClassSessionRead` carries `student_count` / `marked_count`; a student should not receive class-wide attendance aggregates by accident. |
| D2 | Include `cancelled` and `rescheduled` sessions | Hiding them would make a moved or cancelled class disappear from the calendar. The FE labels them explicitly. |
| D3 | Include future sessions | The weekly/monthly view answers "when and where do I attend", not just "what did I miss". |
| D4 | Return holidays as rows, not just missing sessions | A holiday is a calendar label, not an absence of classes: the student must still see the day and its name. |
| D5 | Attendance is read from the caller's `Attendance` row only | Reuses the AI-155 uniqueness rule and prevents cross-student leakage. |
| D6 | `subject` falls back to the class name when `schedule_id` is null | Ad-hoc sessions and sessions whose template was deleted still need a label. |
| D7 | No migration | AI-155 already provides `class_schedule`, `class_session`, `holiday`, and `attendance`. |

---

## 4. Service flow

`attendance_service.get_student_schedule`:

1. Verify an ACTIVE enrollment for `(class_id, student_id)`.
2. Materialise sessions with `schedule_service.generate_sessions`.
3. Query all sessions in range and only the caller's attendance rows.
4. Resolve schedule subjects and trainer names in bulk.
5. Resolve holidays through `holiday_service.holidays_between`.
6. Read `ClassInfo.meeting_url` when present.
7. Build the response with server `today`.

---

## 5. Out of scope

* Editing, cancelling, or rescheduling sessions from the student view.
* Attendance marking (teacher-only, AI-136).
* Holiday CRUD (AI-140).
* Notifications or reminders.
* Room/location fields: the schema from AI-155 has no room column; the class
  information `meeting_url` is shown instead.

---

## 6. Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_attendance_service.py tests\attendance\test_attendance_router.py -q
.\.venv\Scripts\ruff.exe check app\schemas\attendance.py app\services\attendance_service.py app\routers\attendance\student_router.py tests\test_attendance_service.py tests\attendance\test_attendance_router.py
```

Covered by:

* `test_student_schedule_includes_future_sessions_holidays_and_own_status`
* `test_student_schedule_rejects_non_enrolled_student`
* `test_student_schedule_endpoint` (auth, permissions, future session, holiday,
  own status, invalid range)
