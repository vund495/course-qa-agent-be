# AI-140: Holidays and admin-reviewed trainer leave

AI-140 extends AI-158's `leave_request` table. There is no separate trainer-leave table. Run Alembic through `0047_admin_leave` before starting the updated API. Legacy reason text and coverage links remain intact; legacy requests may have no class scope.

## Leave workflow

Trainers create a class-scoped request from the class Attendance page. The request includes `class_id`, `date_from`, `date_to`, `reason_type`, optional `reason_details`, and optional `target_trainer_id`. The existing target field name is retained for compatibility; for new requests it identifies an active teaching assistant assigned to the class. TA assignment reuses the existing active `enrollment` association. Requests are valid without any selected assistant.

Reason codes: `annual_leave`, `sick_leave`, `wedding_leave`, `bereavement_leave`, `maternity_paternity`, `family_care`, `business_trip`, `training_leave`, `civic_duty`, `personal_leave`, `other`. Details are mandatory for `other` on new submissions.

- `POST /api/leave-requests`: create as trainer.
- `GET /api/leave-requests/mine`: the trainer's own requests and decisions.
- `GET /api/admin/leaves?status=pending`: admin notification/review queue; the navigation count links here.
- `POST /api/admin/leaves/{id}/review`: `{ "approve": true }` or `{ "approve": false, "rejection_reason": "..." }`.
- `GET /api/classes/{id}/assistants`: assigned active TAs.
- `POST /api/admin/classes/{id}/assistants`: assign using `{ "assistant_id": "..." }`.
- `DELETE /api/admin/classes/{id}/assistants/{assistant_id}`: unassign; blocked while the assistant is selected for a pending/current/future approved request.

Stored statuses stay `pending`, `accepted` (admin approved), and `rejected`. Only admins can decide leave requests; peer acceptance no longer approves leave. Ticket handover accept/reject APIs are unchanged.

## Availability and tickets

Approved leave makes a trainer effectively off during the inclusive date range, in Vietnam time. Future approval does not transfer today's tickets. The existing lifecycle worker applies current approved leave every 60 seconds; ticket creation and trainer inbox access also check current availability.

During the absence, the selected active class assistant is preferred for the request's class. Available trainers remain the fallback; if nobody is available, tickets wait in the admin queue. OPEN and ANSWERED tickets can be transferred. Transfers use an expected-owner conditional update so a stale sweep cannot overwrite another transfer. Selected assistants can view and answer class tickets; student attendance queries exclude TA enrollments.

Daily present/off buttons require confirmation. Returning to present does not reclaim already-transferred tickets, and an approved leave cannot be overridden by the daily present action.

## Holiday calendar

Admins manage system/class holidays at `/admin/holidays` using `GET`/`POST /api/admin/holidays`, `PUT`/`DELETE /api/admin/holidays/{id}`. Class members read applicable entries at `GET /api/classes/{id}/holidays?year=2026`. Existing session records remain intact and expose holiday and approved-leave warnings. Existing recurring-session generation continues to skip holidays.

## Migration rollback

The migration preserves old rows and copies free-text reasons to `reason_details`. Downgrade refuses to discard new requests with no cover, because the old schema requires a target. Resolve those rows explicitly before requesting a downgrade.
