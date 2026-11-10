"""Handover accept/reject endpoint tests (AI-158 Phase 5)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.ticket import Ticket
from app.models.user import User
from app.services import handover_service


def _headers(user_id: uuid.UUID, role: str) -> dict[str, str]:
    token = create_access_token(str(user_id), role)
    return {"Authorization": f"Bearer {token}"}


def _ticket(db: Session) -> Ticket:
    ticket = Ticket(
        class_id=db.info["class_id"],
        student_id=db.info["student_id"],
        question="Pending handover question",
        citations=[],
        status="OPEN",
        owner_trainer_id=db.info["primary_id"],
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_accept_pending_handover(
    handover_client: TestClient, handover_db: Session
):
    ticket = _ticket(handover_db)
    co_id = handover_db.info["co_trainer_id"]
    co_user = handover_db.query(User).filter(User.id == co_id).one()
    handover = handover_service.assign(
        handover_db,
        ticket,
        co_user,
        "manual_transfer",
        handover_db.info["primary_id"],
        status="pending",
    )
    assert ticket.owner_trainer_id == handover_db.info["primary_id"]

    co_headers = _headers(co_id, "trainer")
    res = handover_client.get("/api/handovers/mine", headers=co_headers)
    assert res.status_code == 200
    assert [row["id"] for row in res.json()] == [str(handover.id)]

    res = handover_client.post(
        f"/api/handovers/{handover.id}/accept", headers=co_headers
    )
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"
    handover_db.refresh(ticket)
    assert ticket.owner_trainer_id == co_id

    res = handover_client.post(
        f"/api/handovers/{handover.id}/accept", headers=co_headers
    )
    assert res.status_code == 409


def test_reject_pending_handover(
    handover_client: TestClient, handover_db: Session
):
    ticket = _ticket(handover_db)
    co_id = handover_db.info["co_trainer_id"]
    co_user = handover_db.query(User).filter(User.id == co_id).one()
    handover = handover_service.assign(
        handover_db,
        ticket,
        co_user,
        "manual_transfer",
        handover_db.info["primary_id"],
        status="pending",
    )

    other_headers = _headers(handover_db.info["other_trainer_id"], "trainer")
    res = handover_client.post(
        f"/api/handovers/{handover.id}/reject", headers=other_headers
    )
    assert res.status_code == 403

    co_headers = _headers(co_id, "trainer")
    res = handover_client.post(
        f"/api/handovers/{handover.id}/reject", headers=co_headers
    )
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"
    handover_db.refresh(ticket)
    assert ticket.owner_trainer_id == handover_db.info["primary_id"]
    assert ticket.queued_for_admin_at is not None
