"""Student-created support tickets (AI-81, AI-89)."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.ticket import Ticket, TicketAttachment
from app.models.user import User
from app.schemas.handover import HandoverAssignRequest, HandoverRead
from app.schemas.tickets import (
    TicketAttachmentRead,
    TicketCountsResponse,
    TicketCreate,
    TicketListResponse,
    TicketRead,
    TicketReplyCreate,
    TicketReplyRead,
    TicketStatus,
    TicketThreadRead,
)
from app.services import course_service, handover_service, ticket_attachment_service, ticket_service
from app.services.course_service import DomainError
from app.services.ticket_attachment_service import AttachmentError
from app.services.user_service import role_name_of

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def _role(user: User) -> str:
    return (role_name_of(user) or "").upper()


def _require_student(user: User) -> None:
    if _role(user) != "STUDENT":
        raise HTTPException(status_code=403, detail="Only students can create or update tickets.")


def _require_admin(user: User) -> None:
    if _role(user) != "ADMIN":
        raise HTTPException(status_code=403, detail="Only admins can do this.")


def _visible_ticket(db: Session, *, ticket_id: uuid.UUID, user: User) -> Ticket:
    """Resolve a ticket the caller can read, regardless of its status."""
    role = _role(user)
    if role == "ADMIN":
        ticket = ticket_service.get_admin_ticket(db, ticket_id)
    elif role == "STUDENT":
        ticket = ticket_service.get_student_ticket(db, ticket_id=ticket_id, student_id=user.id)
    elif role in ("TRAINER", "TEACHING_ASSISTANT"):
        try:
            ticket = ticket_service.get_trainer_ticket(
                db,
                ticket_id=ticket_id,
                trainer_id=user.id,
                class_wide=role == "TEACHING_ASSISTANT",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    else:
        raise HTTPException(
            status_code=403, detail="Only ticket participants can access attachments."
        )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


def _media_ticket(db: Session, *, ticket_id: uuid.UUID, user: User) -> Ticket:
    """Tickets accept new media only while they are open or answered."""
    ticket = _visible_ticket(db, ticket_id=ticket_id, user=user)
    if ticket.status not in ("OPEN", "ANSWERED"):
        raise HTTPException(
            status_code=409,
            detail="Only open or answered tickets can receive attachments.",
        )
    return ticket


@router.get("", response_model=TicketListResponse)
def list_tickets(
    class_id: uuid.UUID | None = None,
    status: TicketStatus | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketListResponse:
    role = _role(user)
    if role == "ADMIN":
        items = ticket_service.list_admin_queue(db)
        total = len(items)
        start = (page - 1) * page_size
        return TicketListResponse(
            items=items[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
        )
    if role not in ("TRAINER", "TEACHING_ASSISTANT"):
        raise HTTPException(status_code=403, detail="Only trainers can view the ticket inbox.")
    try:
        items, total = ticket_service.list_trainer_tickets(
            db,
            trainer_id=user.id,
            class_id=class_id,
            status=status,
            page=page,
            page_size=page_size,
            class_wide=role == "TEACHING_ASSISTANT",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return TicketListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketRead:
    _require_student(user)
    ticket = ticket_service.create_student_ticket(
        db,
        student=user,
        class_id=payload.class_id,
        question=payload.question,
        original_question=payload.original_question,
        agent_answer=payload.agent_answer,
        details=payload.details,
    )
    if ticket is None:
        raise HTTPException(status_code=403, detail="You are not an active member of this class.")
    return TicketRead.model_validate(ticket)


@router.get("/counts", response_model=TicketCountsResponse)
def get_ticket_counts(
    class_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketCountsResponse:
    """AC-03: open/completed ticket counts for each assigned class."""
    if role_name_of(user) not in ("TRAINER", "TEACHING_ASSISTANT"):
        raise HTTPException(status_code=403, detail="Only trainers can view ticket counts.")
    try:
        items = ticket_service.ticket_counts_for_trainer(
            db,
            trainer_id=user.id,
            class_id=class_id,
            class_wide=role_name_of(user) == "TEACHING_ASSISTANT",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return TicketCountsResponse(
        items=items,
        open_total=sum(item.open_count for item in items),
        completed_total=sum(item.completed_count for item in items),
    )


@router.get("/mine", response_model=TicketListResponse)
def list_my_tickets(
    class_id: uuid.UUID | None = None,
    status: TicketStatus | None = None,
    unread: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketListResponse:
    """Student-only list of the caller's own tickets."""
    if role_name_of(user) != "STUDENT":
        raise HTTPException(status_code=403, detail="Only students can view their own tickets.")
    items, total = ticket_service.list_student_tickets(
        db,
        student_id=user.id,
        class_id=class_id,
        status=status,
        unread=unread,
        page=page,
        page_size=page_size,
    )
    return TicketListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/{ticket_id}/seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_ticket_seen(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    _require_student(user)
    if ticket_service.mark_ticket_seen(db, ticket_id=ticket_id, student_id=user.id) is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")


@router.get("/{ticket_id}", response_model=TicketThreadRead)
def get_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketThreadRead:
    role = _role(user)
    if role == "ADMIN":
        ticket = ticket_service.get_admin_ticket(db, ticket_id)
    elif role in ("TRAINER", "TEACHING_ASSISTANT"):
        try:
            ticket = ticket_service.get_trainer_ticket(
                db,
                ticket_id=ticket_id,
                trainer_id=user.id,
                class_wide=role == "TEACHING_ASSISTANT",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    else:
        _require_student(user)
        ticket = ticket_service.get_student_ticket(db, ticket_id=ticket_id, student_id=user.id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return TicketThreadRead.model_validate(ticket)


@router.post("/{ticket_id}/resolve", response_model=TicketRead)
def resolve_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketRead:
    """AC-01: the student confirms, or the assigned trainer marks it handled."""
    role = _role(user)
    if role == "ADMIN":
        existing = ticket_service.get_admin_ticket(db, ticket_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        ticket = ticket_service.resolve_admin_ticket(db, ticket_id=ticket_id)
        if ticket is None:
            raise HTTPException(
                status_code=409, detail="Only an open or answered ticket can be resolved."
            )
        return TicketRead.model_validate(ticket)
    if role in ("TRAINER", "TEACHING_ASSISTANT"):
        try:
            existing = ticket_service.get_trainer_ticket(
                db,
                ticket_id=ticket_id,
                trainer_id=user.id,
                class_wide=role == "TEACHING_ASSISTANT",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if existing is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        ticket = ticket_service.resolve_trainer_ticket(
            db,
            ticket_id=ticket_id,
            trainer_id=user.id,
            class_wide=role == "TEACHING_ASSISTANT",
        )
        if ticket is None:
            raise HTTPException(
                status_code=409, detail="Only an open or answered ticket can be resolved."
            )
        return TicketRead.model_validate(ticket)
    if role != "STUDENT":
        raise HTTPException(
            status_code=403, detail="Only students and assigned trainers can resolve tickets."
        )
    existing = ticket_service.get_student_ticket(db, ticket_id=ticket_id, student_id=user.id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    ticket = ticket_service.resolve_student_ticket(db, ticket_id=ticket_id, student_id=user.id)
    if ticket is None:
        raise HTTPException(status_code=409, detail="Only an answered ticket can be resolved.")
    return TicketRead.model_validate(ticket)


@router.post("/{ticket_id}/reopen", response_model=TicketRead)
def reopen_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketRead:
    """AC-02: reopen a resolved ticket back to Answered, or Open without a reply."""
    role = _role(user)
    if role == "ADMIN":
        existing = ticket_service.get_admin_ticket(db, ticket_id)
    elif role in ("TRAINER", "TEACHING_ASSISTANT"):
        try:
            existing = ticket_service.get_trainer_ticket(
                db,
                ticket_id=ticket_id,
                trainer_id=user.id,
                class_wide=role == "TEACHING_ASSISTANT",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    elif role == "STUDENT":
        existing = ticket_service.get_student_ticket(db, ticket_id=ticket_id, student_id=user.id)
    else:
        raise HTTPException(
            status_code=403, detail="Only students and assigned trainers can reopen tickets."
        )
    if existing is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    ticket = ticket_service.reopen_ticket(db, ticket_id=ticket_id)
    if ticket is None:
        raise HTTPException(status_code=409, detail="Only a resolved ticket can be reopened.")
    return TicketRead.model_validate(ticket)


@router.post(
    "/{ticket_id}/attachments",
    response_model=list[TicketAttachmentRead],
    status_code=status.HTTP_201_CREATED,
)
async def upload_ticket_attachments(
    ticket_id: uuid.UUID,
    files: list[UploadFile] | None = File(default=None),
    emojis: list[str] | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TicketAttachmentRead]:
    """Upload images and/or emojis that the next reply will carry.

    Files are validated by content (PNG/JPEG/WEBP/GIF, max 5 MB each) and stay
    unbound until ``POST /{ticket_id}/replies`` sends their ids.
    """
    ticket = _media_ticket(db, ticket_id=ticket_id, user=user)
    uploads_files = files or []
    emoji_values = emojis or []
    if not uploads_files and not emoji_values:
        raise HTTPException(status_code=400, detail="Attach at least one image or emoji.")
    uploads: list[tuple[str, bytes]] = []
    for upload in uploads_files:
        uploads.append((upload.filename or "image", await upload.read()))
    try:
        created = ticket_attachment_service.save_images(
            db, ticket=ticket, user_id=user.id, uploads=uploads
        )
        created += ticket_attachment_service.save_emojis(
            db, ticket=ticket, user_id=user.id, emojis=emoji_values
        )
    except AttachmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [TicketAttachmentRead.model_validate(item) for item in created]


@router.get("/attachments/{attachment_id}")
def download_ticket_attachment(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """Serve an attached image inline to ticket participants only."""
    record = db.query(TicketAttachment).filter(TicketAttachment.id == attachment_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    _visible_ticket(db, ticket_id=record.ticket_id, user=user)
    if record.kind != "IMAGE":
        raise HTTPException(status_code=415, detail="Emoji attachments carry no file.")
    path = ticket_attachment_service.image_path(record)
    if path is None:
        raise HTTPException(status_code=404, detail="Attachment file is missing.")
    return FileResponse(
        path,
        media_type=record.mime_type or "application/octet-stream",
        filename=record.file_name or "image",
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket_attachment(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Drop an attachment the caller uploaded but has not sent yet."""
    record = db.query(TicketAttachment).filter(TicketAttachment.id == attachment_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    _visible_ticket(db, ticket_id=record.ticket_id, user=user)
    if not ticket_attachment_service.delete_pending(
        db, attachment_id=attachment_id, user_id=user.id
    ):
        raise HTTPException(
            status_code=409,
            detail="Only your own unsent attachment can be removed.",
        )


@router.post("/{ticket_id}/replies", response_model=TicketReplyRead, status_code=201)
def add_ticket_reply(
    ticket_id: uuid.UUID,
    payload: TicketReplyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketReplyRead:
    role = _role(user)
    if role == "ADMIN":
        reply = ticket_service.add_admin_reply(
            db,
            ticket_id=ticket_id,
            admin_id=user.id,
            message=payload.message,
        )
        if reply is None:
            raise HTTPException(status_code=409, detail="Only open tickets can be answered.")
    elif role == "STUDENT":
        existing = ticket_service.get_student_ticket(db, ticket_id=ticket_id, student_id=user.id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        if existing.status not in ("OPEN", "ANSWERED"):
            raise HTTPException(
                status_code=409,
                detail="Only open or answered tickets can receive follow-up messages.",
            )
        reply = ticket_service.add_student_reply(
            db,
            ticket_id=ticket_id,
            student_id=user.id,
            message=payload.message,
        )
    elif role in ("TRAINER", "TEACHING_ASSISTANT"):
        try:
            reply = ticket_service.add_trainer_reply(
                db,
                ticket_id=ticket_id,
                trainer_id=user.id,
                message=payload.message,
                class_wide=role == "TEACHING_ASSISTANT",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if reply is None:
            raise HTTPException(
                status_code=409, detail="Only open or answered tickets can be answered."
            )
    else:
        raise HTTPException(
            status_code=403, detail="Only students and assigned trainers can reply."
        )
    if reply is None:
        raise HTTPException(
            status_code=409, detail="Only open tickets can receive follow-up messages."
        )
    if payload.attachment_ids:
        try:
            ticket_attachment_service.bind_to_reply(
                db, reply=reply, attachment_ids=payload.attachment_ids
            )
        except AttachmentError as exc:
            # Keep the thread consistent: an invalid attachment must not leave
            # a reply behind that the sender cannot see media for.
            db.delete(reply)
            db.commit()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TicketReplyRead.model_validate(reply)


@router.post("/{ticket_id}/handover", response_model=HandoverRead)
def assign_ticket(
    ticket_id: uuid.UUID,
    payload: HandoverAssignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HandoverRead:
    """Admin-only manual transfer within the ticket's class (Phase 4)."""
    _require_admin(user)
    ticket = ticket_service.get_admin_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    target = db.query(User).filter(User.id == payload.to_trainer_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Trainer not found.")
    class_trainer_ids = {
        item["trainer_id"] for item in course_service.list_trainers(db, ticket.class_id)
    }
    class_trainer_ids.update(
        item.id for item in course_service.list_assistants(db, ticket.class_id)
    )
    if target.status != "ACTIVE" or target.id not in class_trainer_ids:
        raise HTTPException(
            status_code=400,
            detail="Target trainer does not teach this class.",
        )

    try:
        handover = handover_service.assign(
            db,
            ticket,
            target,
            "manual_transfer",
            user.id,
            status="accepted",
        )
    except DomainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return HandoverRead.model_validate(handover)
