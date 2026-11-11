"""Planned leave request router tests (AI-158 Phase 5)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.attendance import LeaveRequest, TrainerDayStatus
from app.models.course import ClassTrainer
from app.models.ticket import Ticket
from app.services.holiday_service import VIETNAM_TZ, local_date


def _headers(user_id: uuid.UUID, role: str) -> dict[str, str]:
    token = create_access_token(str(user_id), role)
    return {"Authorization": f"Bearer {token}"}


def _today_iso() -> str:
    return local_date(datetime.now(VIETNAM_TZ)).isoformat()


def _ticket(db: Session, owner_id: uuid.UUID) -> Ticket:
    ticket = Ticket(
        class_id=db.info["class_id"],
        student_id=db.info["student_id"],
        question="Leave coverage question",
        citations=[],
        status="OPEN",
        owner_trainer_id=owner_id,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_create_leave_and_validate_target(
    handover_client: TestClient, handover_db: Session
):
    primary = _headers(handover_db.info["primary_id"], "trainer")
    co_id = handover_db.info["co_trainer_id"]
    other_id = handover_db.info["other_trainer_id"]

    res = handover_client.post(
        "/api/leave-requests",
        json={
            "date_from": _today_iso(),
            "date_to": _today_iso(),
            "target_trainer_id": str(co_id),
            "reason": "  Family trip  ",
        },
        headers=primary,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "pending"
    assert body["trainer_name"] == "Primary Trainer"
    assert body["target_trainer_name"] == "Co Trainer"
    assert body["reason"] == "Family trip"

    res = handover_client.post(
        "/api/leave-requests",
        json={
            "date_from": _today_iso(),
            "date_to": _today_iso(),
            "target_trainer_id": str(handover_db.info["primary_id"]),
        },
        headers=primary,
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "You cannot delegate to yourself."

    res = handover_client.post(
        "/api/leave-requests",
        json={
            "date_from": _today_iso(),
            "date_to": _today_iso(),
            "target_trainer_id": str(other_id),
        },
        headers=primary,
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Target trainer does not teach this class."

    today = local_date(datetime.now(VIETNAM_TZ))
    res = handover_client.post(
        "/api/leave-requests",
        json={
            "date_from": (today + timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
            "target_trainer_id": str(co_id),
        },
        headers=primary,
    )
    assert res.status_code == 422


def test_accept_leave_marks_off_and_prefers_target(
    handover_client: TestClient, handover_db: Session
):
    primary_id = handover_db.info["primary_id"]
    co_id = handover_db.info["co_trainer_id"]
    primary = _headers(primary_id, "trainer")
    co = _headers(co_id, "trainer")
    student = _headers(handover_db.info["student_id"], "student")
    ticket = _ticket(handover_db, primary_id)

    res = handover_client.post(
        "/api/leave-requests",
        json={
            "date_from": _today_iso(),
            "date_to": _today_iso(),
            "target_trainer_id": str(co_id),
        },
        headers=primary,
    )
    leave_id = res.json()["id"]

    res = handover_client.get("/api/leave-requests/mine", headers=co)
    assert res.status_code == 200
    assert any(item["id"] == leave_id for item in res.json())

    res = handover_client.post(f"/api/leave-requests/{leave_id}/accept", headers=co)
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"

    handover_db.refresh(ticket)
    assert ticket.owner_trainer_id == co_id
    assert ticket.queued_for_admin_at is None
    status = (
        handover_db.query(TrainerDayStatus)
        .filter(
            TrainerDayStatus.trainer_id == primary_id,
            TrainerDayStatus.date == local_date(datetime.now(VIETNAM_TZ)),
        )
        .one()
    )
    assert status.status == "off"

    res = handover_client.post(
        "/api/tickets",
        json={"class_id": str(handover_db.info["class_id"]), "question": "New in range"},
        headers=student,
    )
    assert res.status_code == 201
    assert res.json()["owner_trainer_id"] == str(co_id)


def test_manual_priority_beats_least_open(handover_db: Session):
    primary_id = handover_db.info["primary_id"]
    co_id = handover_db.info["co_trainer_id"]
    other_id = handover_db.info["other_trainer_id"]
    handover_db.add(
        ClassTrainer(class_id=handover_db.info["class_id"], trainer_id=other_id)
    )
    handover_db.commit()

    leave = LeaveRequest(
        trainer_id=primary_id,
        date_from=local_date(datetime.now(VIETNAM_TZ)),
        date_to=local_date(datetime.now(VIETNAM_TZ)),
        target_trainer_id=co_id,
        status="accepted",
    )
    handover_db.add(leave)
    _ticket(handover_db, co_id)
    ticket = _ticket(handover_db, primary_id)
    handover_db.commit()

    from app.services.handover_service import sweep_for_trainer

    handled = sweep_for_trainer(
        handover_db, primary_id, local_date(datetime.now(VIETNAM_TZ))
    )
    assert handled == 1
    handover_db.refresh(ticket)
    assert ticket.owner_trainer_id == co_id


def test_reject_leave_falls_back_to_auto(
    handover_client: TestClient, handover_db: Session
):
    primary_id = handover_db.info["primary_id"]
    co_id = handover_db.info["co_trainer_id"]
    primary = _headers(primary_id, "trainer")
    co = _headers(co_id, "trainer")
    other = _headers(handover_db.info["other_trainer_id"], "trainer")
    ticket = _ticket(handover_db, primary_id)

    res = handover_client.post(
        "/api/leave-requests",
        json={
            "date_from": _today_iso(),
            "date_to": _today_iso(),
            "target_trainer_id": str(co_id),
        },
        headers=primary,
    )
    leave_id = res.json()["id"]

    res = handover_client.post(f"/api/leave-requests/{leave_id}/reject", headers=other)
    assert res.status_code == 403

    res = handover_client.post(f"/api/leave-requests/{leave_id}/reject", headers=co)
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"
    handover_db.refresh(ticket)
    assert ticket.queued_for_admin_at is not None
    assert ticket.owner_trainer_id == primary_id

    res = handover_client.post(f"/api/leave-requests/{leave_id}/accept", headers=co)
    assert res.status_code == 409
