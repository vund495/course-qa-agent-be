"""Planned leave request router tests (AI-158 Phase 5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.attendance import LeaveRequest
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


def test_manual_priority_beats_least_open(handover_db: Session):
    primary_id = handover_db.info["primary_id"]
    co_id = handover_db.info["co_trainer_id"]
    other_id = handover_db.info["other_trainer_id"]
    handover_db.add(ClassTrainer(class_id=handover_db.info["class_id"], trainer_id=other_id))
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

    handled = sweep_for_trainer(handover_db, primary_id, local_date(datetime.now(VIETNAM_TZ)))
    assert handled == 1
    handover_db.refresh(ticket)
    assert ticket.owner_trainer_id == co_id


def test_peer_cannot_approve_leave(handover_client, handover_db):
    leave = LeaveRequest(
        trainer_id=handover_db.info["primary_id"],
        date_from=local_date(datetime.now(VIETNAM_TZ)),
        date_to=local_date(datetime.now(VIETNAM_TZ)),
        target_trainer_id=handover_db.info["co_trainer_id"],
        status="pending",
    )
    handover_db.add(leave)
    handover_db.commit()
    headers = _headers(handover_db.info["co_trainer_id"], "trainer")
    assert (
        handover_client.post(f"/api/leave-requests/{leave.id}/accept", headers=headers).status_code
        == 403
    )
    assert (
        handover_client.post(f"/api/leave-requests/{leave.id}/reject", headers=headers).status_code
        == 403
    )


def test_trainer_can_read_own_admin_decision(handover_client, handover_db):
    leave = LeaveRequest(
        trainer_id=handover_db.info["primary_id"],
        date_from=local_date(datetime.now(VIETNAM_TZ)),
        date_to=local_date(datetime.now(VIETNAM_TZ)),
        status="rejected",
        rejection_reason="Reschedule",
    )
    handover_db.add(leave)
    handover_db.commit()
    response = handover_client.get(
        "/api/leave-requests/mine", headers=_headers(handover_db.info["primary_id"], "trainer")
    )
    assert response.status_code == 200
    assert response.json()[0]["rejection_reason"] == "Reschedule"
    assert (
        handover_client.get(
            "/api/leave-requests/mine",
            headers=_headers(handover_db.info["co_trainer_id"], "trainer"),
        ).json()
        == []
    )
