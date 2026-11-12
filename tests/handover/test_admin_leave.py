"""Admin leave review and optional class coverage."""

from datetime import UTC, datetime, timedelta

from app.core.security import create_access_token
from app.models.course import Enrollment
from app.models.ticket import Ticket
from app.models.user import Role, User
from app.services.holiday_service import local_date


def headers(db, key):
    return {
        "Authorization": "Bearer "
        + create_access_token(str(db.info[key]), "admin" if key == "admin_id" else "trainer")
    }


def payload(db, **extra):
    day = str(local_date(datetime.now(UTC)))
    return {
        "class_id": str(db.info["class_id"]),
        "date_from": day,
        "date_to": day,
        "reason_type": "sick_leave",
        **extra,
    }


def test_admin_reviews_leave_without_cover(handover_client, handover_db):
    db, client = handover_db, handover_client
    res = client.post("/api/leave-requests", json=payload(db), headers=headers(db, "primary_id"))
    assert res.status_code == 201, res.text
    leave = res.json()
    assert leave["target_trainer_id"] is None
    assert leave["class_name"] == "AI-158 Router Class 2"
    assert (
        client.get("/api/admin/leaves?status=pending", headers=headers(db, "admin_id")).json()[0][
            "id"
        ]
        == leave["id"]
    )
    url = f"/api/admin/leaves/{leave['id']}/review"
    assert (
        client.post(url, json={"approve": True}, headers=headers(db, "primary_id")).status_code
        == 403
    )
    assert (
        client.post(
            url,
            json={"approve": False, "rejection_reason": "Reschedule"},
            headers=headers(db, "admin_id"),
        ).json()["rejection_reason"]
        == "Reschedule"
    )
    changed = client.post(
        url,
        json={"approve": True},
        headers=headers(db, "admin_id"),
    )
    assert changed.status_code == 200
    assert changed.json()["status"] == "accepted"
    assert changed.json()["rejection_reason"] is None

    assert (
        client.post(url, json={"approve": True}, headers=headers(db, "admin_id")).status_code
        == 409
    )


def test_admin_changes_approved_leave_to_rejected_without_reclaiming_ticket(
    handover_client, handover_db
):
    db, client = handover_db, handover_client
    ticket = Ticket(
        class_id=db.info["class_id"],
        student_id=db.info["student_id"],
        question="Keep the current owner after a decision change",
        owner_trainer_id=db.info["primary_id"],
        status="OPEN",
    )
    db.add(ticket)
    db.commit()

    leave = client.post(
        "/api/leave-requests",
        json=payload(db),
        headers=headers(db, "primary_id"),
    ).json()
    url = f"/api/admin/leaves/{leave['id']}/review"

    approved = client.post(
        url,
        json={"approve": True},
        headers=headers(db, "admin_id"),
    )
    assert approved.status_code == 200
    db.refresh(ticket)
    transferred_owner = ticket.owner_trainer_id
    assert transferred_owner != db.info["primary_id"]

    rejected = client.post(
        url,
        json={"approve": False, "rejection_reason": "Schedule changed"},
        headers=headers(db, "admin_id"),
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Schedule changed"
    db.refresh(ticket)
    assert ticket.owner_trainer_id == transferred_owner

    status = client.get(
        "/api/trainer-status",
        headers=headers(db, "primary_id"),
    )
    assert status.status_code == 200
    assert status.json()["status"] == "present"


def test_assistant_receives_existing_and_new_tickets(handover_client, handover_db):
    db, client = handover_db, handover_client
    role = db.query(Role).filter_by(name="TEACHING_ASSISTANT").one()
    assistant = User(
        full_name="Class Assistant", email="ta@test.test", role_id=role.id, status="ACTIVE"
    )
    db.add(assistant)
    db.flush()
    db.add(Enrollment(class_id=db.info["class_id"], student_id=assistant.id, status="ACTIVE"))
    ticket = Ticket(
        class_id=db.info["class_id"],
        student_id=db.info["student_id"],
        question="Cover",
        owner_trainer_id=db.info["primary_id"],
        status="OPEN",
    )
    db.add(ticket)
    db.commit()
    res = client.post(
        "/api/leave-requests",
        json=payload(db, target_trainer_id=str(assistant.id)),
        headers=headers(db, "primary_id"),
    )
    assert res.status_code == 201, res.text
    res = client.post(
        f"/api/admin/leaves/{res.json()['id']}/review",
        json={"approve": True},
        headers=headers(db, "admin_id"),
    )
    assert res.status_code == 200, res.text
    db.refresh(ticket)
    assert ticket.owner_trainer_id == assistant.id
    from app.services.ticket_service import create_student_ticket

    new = create_student_ticket(
        db,
        student=db.get(User, db.info["student_id"]),
        class_id=db.info["class_id"],
        question="New",
    )
    assert new.owner_trainer_id == assistant.id
    auth = {
        "Authorization": "Bearer " + create_access_token(str(assistant.id), "teaching_assistant")
    }
    assert client.get("/api/tickets", headers=auth).status_code == 200
    assert client.get("/api/handovers/mine", headers=auth).status_code == 200
    assert (
        client.post(
            f"/api/tickets/{new.id}/replies", json={"message": "Help"}, headers=auth
        ).status_code
        == 201
    )


def test_future_leave_does_not_transfer_today(handover_client, handover_db):
    db, client = handover_db, handover_client
    ticket = Ticket(
        class_id=db.info["class_id"],
        student_id=db.info["student_id"],
        question="Wait",
        owner_trainer_id=db.info["primary_id"],
    )
    db.add(ticket)
    db.commit()
    future = str(local_date(datetime.now(UTC)) + timedelta(days=14))
    res = client.post(
        "/api/leave-requests",
        json=payload(db, date_from=future, date_to=future),
        headers=headers(db, "primary_id"),
    )
    assert res.status_code == 201, res.text
    assert (
        client.post(
            f"/api/admin/leaves/{res.json()['id']}/review",
            json={"approve": True},
            headers=headers(db, "admin_id"),
        ).status_code
        == 200
    )
    db.refresh(ticket)
    assert ticket.owner_trainer_id == db.info["primary_id"]


def test_invalid_reason_and_unassigned_target(handover_client, handover_db):
    db, client = handover_db, handover_client
    for extra, code in [
        ({"reason_type": "invalid"}, 422),
        ({"reason_type": "other"}, 422),
        ({"target_trainer_id": str(db.info["other_trainer_id"])}, 400),
    ]:
        assert (
            client.post(
                "/api/leave-requests", json=payload(db, **extra), headers=headers(db, "primary_id")
            ).status_code
            == code
        )


def test_approved_leave_queues_answered_ticket_visibly(handover_client, handover_db):
    from app.models.attendance import TrainerDayStatus

    db, client = handover_db, handover_client
    day = local_date(datetime.now(UTC))
    db.add(TrainerDayStatus(trainer_id=db.info["co_trainer_id"], date=day, status="off"))
    ticket = Ticket(
        class_id=db.info["class_id"],
        student_id=db.info["student_id"],
        question="Answered needs coverage",
        owner_trainer_id=db.info["primary_id"],
        status="ANSWERED",
    )
    db.add(ticket)
    db.commit()
    row = client.post(
        "/api/leave-requests", json=payload(db), headers=headers(db, "primary_id")
    ).json()
    assert (
        client.post(
            f"/api/admin/leaves/{row['id']}/review",
            json={"approve": True},
            headers=headers(db, "admin_id"),
        ).status_code
        == 200
    )
    queue = client.get("/api/admin/tickets/queue", headers=headers(db, "admin_id")).json()
    assert any(item["id"] == str(ticket.id) for item in queue)
    assert "Primary Trainer" in queue[0]["absent_trainers"]

    rejected = client.post(
        f"/api/admin/leaves/{row['id']}/review",
        json={"approve": False},
        headers=headers(db, "admin_id"),
    )
    assert rejected.status_code == 200
    db.refresh(ticket)
    assert ticket.owner_trainer_id == db.info["primary_id"]
    assert ticket.queued_for_admin_at is None


def test_stale_transfer_cannot_overwrite_new_owner(handover_db):
    import pytest
    from sqlalchemy import update

    from app.services.handover_service import HandoverConflictError, assign

    db = handover_db
    ticket = Ticket(
        class_id=db.info["class_id"],
        student_id=db.info["student_id"],
        question="Concurrent cover",
        owner_trainer_id=db.info["primary_id"],
        status="OPEN",
    )
    db.add(ticket)
    db.commit()
    db.execute(
        update(Ticket)
        .where(Ticket.id == ticket.id)
        .values(owner_trainer_id=db.info["co_trainer_id"])
        .execution_options(synchronize_session=False)
    )
    db.commit()
    with pytest.raises(HandoverConflictError):
        assign(
            db,
            ticket,
            db.get(User, db.info["other_trainer_id"]),
            "auto_absent",
            db.info["primary_id"],
        )
    db.refresh(ticket)
    assert ticket.owner_trainer_id == db.info["co_trainer_id"]


def test_assistant_assignment_uses_existing_membership(handover_client, handover_db):
    db, client = handover_db, handover_client
    role = db.query(Role).filter_by(name="TEACHING_ASSISTANT").one()
    assistant = User(
        full_name="Assigned TA", email="assigned@test.test", role_id=role.id, status="ACTIVE"
    )
    db.add(assistant)
    db.commit()
    path = f"/api/admin/classes/{db.info['class_id']}/assistants"
    assert (
        client.post(
            path, json={"assistant_id": str(assistant.id)}, headers=headers(db, "primary_id")
        ).status_code
        == 403
    )
    assert (
        client.post(
            path, json={"assistant_id": str(assistant.id)}, headers=headers(db, "admin_id")
        ).status_code
        == 200
    )
    result = client.get(
        f"/api/classes/{db.info['class_id']}/assistants", headers=headers(db, "primary_id")
    )
    assert result.json()[0]["id"] == str(assistant.id)
    student_headers = {
        "Authorization": "Bearer "
        + create_access_token(str(db.info["student_id"]), "student")
    }
    assert (
        client.get(
            f"/api/classes/{db.info['class_id']}/assistants",
            headers=student_headers,
        ).status_code
        == 403
    )
    assert (
        client.delete(path + "/" + str(assistant.id), headers=headers(db, "admin_id")).status_code
        == 204
    )
    assert (
        client.get(
            f"/api/classes/{db.info['class_id']}/assistants", headers=headers(db, "primary_id")
        ).json()
        == []
    )


def test_all_eleven_reason_codes_are_supported():
    import uuid

    from app.schemas.handover import LeaveRequestCreate

    reasons = [
        "annual_leave",
        "sick_leave",
        "wedding_leave",
        "bereavement_leave",
        "maternity_paternity",
        "family_care",
        "business_trip",
        "training_leave",
        "civic_duty",
        "personal_leave",
        "other",
    ]
    for reason in reasons:
        item = LeaveRequestCreate(
            class_id=uuid.uuid4(),
            date_from="2026-11-12",
            date_to="2026-11-12",
            reason_type=reason,
            reason_details="Details",
        )
        assert item.reason_type == reason


def test_admin_can_manually_transfer_to_class_assistant(handover_client, handover_db):
    db, client = handover_db, handover_client
    from app.models.course import Enrollment

    role = db.query(Role).filter_by(name="TEACHING_ASSISTANT").one()
    assistant = User(
        full_name="Manual TA", email="manual@test.test", role_id=role.id, status="ACTIVE"
    )
    db.add(assistant)
    db.flush()
    db.add(Enrollment(class_id=db.info["class_id"], student_id=assistant.id, status="ACTIVE"))
    ticket = Ticket(
        class_id=db.info["class_id"],
        student_id=db.info["student_id"],
        question="Manual",
        owner_trainer_id=db.info["primary_id"],
    )
    db.add(ticket)
    db.commit()
    res = client.post(
        f"/api/tickets/{ticket.id}/handover",
        json={"to_trainer_id": str(assistant.id)},
        headers=headers(db, "admin_id"),
    )
    assert res.status_code == 200, res.text
    db.refresh(ticket)
    assert ticket.owner_trainer_id == assistant.id
