"""Admin queue, admin reply, and manual assignment tests (AI-158 Phase 4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.attendance import TrainerDayStatus
from app.models.ticket import Ticket
from app.services.holiday_service import VIETNAM_TZ, local_date


def _headers(user_id: uuid.UUID, role: str) -> dict[str, str]:
    token = create_access_token(str(user_id), role)
    return {"Authorization": f"Bearer {token}"}


def _ticket(
    db: Session,
    *,
    queued_at: datetime | None,
    owner_id: uuid.UUID | None = None,
    status: str = "OPEN",
) -> Ticket:
    ticket = Ticket(
        class_id=db.info["class_id"],
        student_id=db.info["student_id"],
        question="Admin queue question",
        citations=[],
        status=status,
        owner_trainer_id=owner_id or db.info["primary_id"],
        queued_for_admin_at=queued_at,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_admin_queue_permissions_and_payload(
    handover_client: TestClient, handover_db: Session
):
    queued = _ticket(
        handover_db,
        queued_at=datetime.now(UTC) - timedelta(hours=1),
    )
    _ticket(handover_db, queued_at=None)
    _ticket(
        handover_db,
        queued_at=datetime.now(UTC),
        status="ANSWERED",
    )
    handover_db.add(
        TrainerDayStatus(
            trainer_id=handover_db.info["co_trainer_id"],
            date=local_date(datetime.now(VIETNAM_TZ)),
            status="off",
            recorded_by=handover_db.info["admin_id"],
        )
    )
    handover_db.commit()

    admin = _headers(handover_db.info["admin_id"], "admin")
    trainer = _headers(handover_db.info["primary_id"], "trainer")
    student = _headers(handover_db.info["student_id"], "student")

    assert handover_client.get("/api/admin/tickets/queue", headers=trainer).status_code == 403
    assert handover_client.get("/api/admin/tickets/queue", headers=student).status_code == 403

    res = handover_client.get("/api/admin/tickets/queue", headers=admin)
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["id"] == str(queued.id)
    assert body[0]["owner_trainer_name"] == "Primary Trainer"
    assert body[0]["absent_trainers"] == ["Co Trainer"]
    assert body[0]["queued_for_admin_at"] is not None

    res = handover_client.get("/api/tickets", headers=admin)
    assert res.status_code == 200
    assert res.json()["total"] == 2
    assert res.json()["items"][0]["id"] == str(queued.id)


def test_admin_reply_closes_queue(
    handover_client: TestClient, handover_db: Session
):
    ticket = _ticket(handover_db, queued_at=datetime.now(UTC))
    admin = _headers(handover_db.info["admin_id"], "admin")

    res = handover_client.post(
        f"/api/tickets/{ticket.id}/replies",
        json={"message": "Admin is looking into this."},
        headers=admin,
    )

    assert res.status_code == 201
    handover_db.refresh(ticket)
    assert ticket.status == "ANSWERED"
    assert ticket.queued_for_admin_at is None
    assert handover_client.get("/api/admin/tickets/queue", headers=admin).json() == []


def test_admin_assign_validation_and_conflicts(
    handover_client: TestClient, handover_db: Session
):
    ticket = _ticket(handover_db, queued_at=datetime.now(UTC))
    admin = _headers(handover_db.info["admin_id"], "admin")
    co_id = handover_db.info["co_trainer_id"]

    res = handover_client.post(
        f"/api/tickets/{ticket.id}/handover",
        json={"to_trainer_id": str(co_id)},
        headers=admin,
    )
    assert res.status_code == 200
    assert res.json()["to_trainer_id"] == str(co_id)
    assert res.json()["reason"] == "manual_transfer"
    handover_db.refresh(ticket)
    assert ticket.owner_trainer_id == co_id
    assert ticket.queued_for_admin_at is None

    res = handover_client.post(
        f"/api/tickets/{ticket.id}/handover",
        json={"to_trainer_id": str(co_id)},
        headers=admin,
    )
    assert res.status_code == 409

    res = handover_client.post(
        f"/api/tickets/{ticket.id}/handover",
        json={"to_trainer_id": str(handover_db.info["other_trainer_id"])},
        headers=admin,
    )
    assert res.status_code == 400

    ticket.status = "RESOLVED"
    handover_db.commit()
    res = handover_client.post(
        f"/api/tickets/{ticket.id}/handover",
        json={"to_trainer_id": str(handover_db.info["primary_id"])},
        headers=admin,
    )
    assert res.status_code == 409


def test_admin_can_resolve_and_reopen(
    handover_client: TestClient, handover_db: Session
):
    ticket = _ticket(handover_db, queued_at=None)
    admin = _headers(handover_db.info["admin_id"], "admin")

    res = handover_client.post(f"/api/tickets/{ticket.id}/resolve", headers=admin)
    assert res.status_code == 200
    assert res.json()["status"] == "RESOLVED"

    res = handover_client.post(f"/api/tickets/{ticket.id}/reopen", headers=admin)
    assert res.status_code == 200
    assert res.json()["status"] == "OPEN"
