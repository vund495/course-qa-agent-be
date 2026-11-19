"""Documents router: upload / list / approve / delete, scoped by class (AI-35/37/41/39).

Auth (AI-25/27): all endpoints require a Bearer JWT for a trainer or admin
via ``app.core.deps.require_trainer``. Identity is the DB ``User`` row;
class scope resolves from ``course``/``class`` tables.
"""

import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_trainer
from app.models.document import Document
from app.models.user import User
from app.schemas.documents import (
    AcceptedTypeRead,
    AttachSyllabusMaterialRequest,
    ClassMineRead,
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentRead,
    DocumentUploadResponse,
    DocumentUploadResult,
    SyllabusMaterialRead,
    TeacherSyllabusRead,
    TeacherSyllabusUnitRead,
)
from app.services import document_service, ingestion_service
from app.services.document_service import ACCEPTED_EXTENSIONS, VALID_STATUSES
from app.services.ingestion.syllabus_parser import (
    SyllabusFormatError,
    is_syllabus_document,
    parse_syllabus_markdown,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _require_uploader(record: Document, user: User) -> None:
    if record.uploaded_by != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the uploader can manage this document.",
        )


def _scoped_document(db: Session, document_id: str, user: User) -> Document:
    record = document_service.get_document(db, document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if record.class_id not in document_service.my_class_ids(db, user):
        raise HTTPException(status_code=403, detail="Class is not assigned to you.")
    return record


def _stored_file(record: Document) -> Path:
    try:
        path = document_service.document_path(record)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document file not found on server.")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document file not found on server.")
    return path


def _is_previewable(record: Document) -> bool:
    return record.mime_type == "application/pdf" or record.mime_type.startswith("image/")


def _record_to_read(db: Session, record: Document) -> DocumentRead:
    return DocumentRead(
        id=str(record.id),
        file_name=record.file_name,
        file_type=record.file_type,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        uploader_id=str(record.uploaded_by),
        class_id=str(record.class_id),
        class_name=document_service.class_name(db, record.class_id),
        status=record.status,
        failure_reason=record.failure_reason,
        version=record.version,
        created_at=record.created_at,
        syllabus_document_id=(
            str(record.syllabus_document_id) if record.syllabus_document_id else None
        ),
        syllabus_unit_number=record.syllabus_unit_number,
    )


@router.get("/accepted-types", response_model=list[AcceptedTypeRead])
def accepted_types(
    _user: User = Depends(require_trainer),
) -> list[AcceptedTypeRead]:
    """Every accepted file type for the upload screen (Upload AC-07)."""
    labels = {
        ".pdf": "PDF document",
        ".docx": "Word document",
        ".md": "Markdown",
        ".txt": "Plain text",
        ".pptx": "PowerPoint",
        ".xlsx": "Excel",
    }
    return [
        AcceptedTypeRead(extension=ext, mime=mime, label=labels[ext])
        for ext, mime in sorted(ACCEPTED_EXTENSIONS.items())
    ]


@router.get("/classes/mine", response_model=list[ClassMineRead])
def classes_mine(
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> list[ClassMineRead]:
    """Classes assigned to the caller (Upload AC-05 / List AC-05)."""
    return [ClassMineRead(**c) for c in document_service.my_classes(db, user)]


@router.post("/", response_model=DocumentUploadResponse, status_code=201)
async def upload_documents(
    files: list[UploadFile] = File(...),
    class_id: str = Form(...),
    syllabus_document_id: str | None = Form(default=None),
    unit_number: int | None = Form(default=None),
    force: bool = Query(default=False),
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    """Multi-file material upload (Upload AC-04); each file validated (AC-06).

    AI-39 AC-03: a repeated file name creates a pending next version; the
    prior version stays active until the replacement is approved and indexed.

    AI-166: optional ``syllabus_document_id`` + ``unit_number`` attach the
    material to one unit of a draft or approved syllabus in the same class.
    """
    if unit_number is not None and syllabus_document_id is None:
        raise HTTPException(
            status_code=400,
            detail="unit_number requires syllabus_document_id.",
        )
    try:
        class_uuid = uuid.UUID(class_id)
    except (TypeError, ValueError, AttributeError):
        class_uuid = None

    target: Document | None = None
    target_error: str | None = None
    if syllabus_document_id is not None:
        if class_uuid is None:
            target_error = "Class does not exist."
        else:
            resolved = document_service.validate_material_target(
                db,
                class_id=class_uuid,
                syllabus_document_id=syllabus_document_id,
                unit_number=unit_number,
                user=user,
            )
            if isinstance(resolved, str):
                target_error = resolved
            else:
                target = resolved

    # Phase 1: create/parse every file first. The syllabus context must be
    # resolved after the whole batch exists, otherwise a material ordered
    # before its new syllabus would bind to NULL or a stale active syllabus.
    prepared: list[dict] = []
    batch_syllabi: list[Document] = []
    for upload in files:
        content = await upload.read()
        name = upload.filename or "unnamed"
        if target_error is not None:
            prepared.append({"name": name, "error": target_error})
            continue
        try:
            record = document_service.create_document(db, name, content, class_id, user)
        except ValueError as exc:
            prepared.append({"name": name, "error": str(exc)})
            continue

        doc_text = ""
        try:
            loaded = ingestion_service._load_document(document_service.document_path(record))
            doc_text = loaded.get("markdown", "")
        except Exception:  # noqa: BLE001 - parser failures surface as warnings/errors
            doc_text = ""
        uploaded_is_syllabus = is_syllabus_document(name, doc_text)

        if target is not None and uploaded_is_syllabus:
            document_service.delete_document(db, record)
            prepared.append(
                {
                    "name": name,
                    "error": "A syllabus file cannot be attached as unit material.",
                }
            )
            continue

        if uploaded_is_syllabus:
            record.is_syllabus = True
            db.commit()
            try:
                roadmap = parse_syllabus_markdown(doc_text)
                document_service.save_draft_syllabus_units(db, record, roadmap)
            except SyllabusFormatError:
                document_service.delete_document(db, record)
                prepared.append(
                    {
                        "name": name,
                        "error": "Syllabus format is not recognized or contains no course units.",
                    }
                )
                continue
            batch_syllabi.append(record)

        prepared.append(
            {"name": name, "record": record, "is_syllabus": uploaded_is_syllabus}
        )

    # Phase 2: resolve the batch syllabus. One new syllabus wins over an older
    # active syllabus; multiple new syllabi without an explicit target are
    # ambiguous and must not silently bind materials to either one.
    selected_target = target
    if selected_target is None and target_error is None:
        if len(batch_syllabi) > 1:
            for entry in prepared:
                record = entry.get("record")
                if record is not None:
                    document_service.delete_document(db, record)
            raise HTTPException(
                status_code=400,
                detail=(
                    "Multiple syllabus files in one upload are ambiguous. "
                    "Upload one syllabus, then attach materials explicitly."
                ),
            )
        if batch_syllabi:
            selected_target = batch_syllabi[0]
        elif class_uuid is not None:
            selected_target, _ = document_service.get_latest_syllabus_record(
                db, class_uuid
            )

    for entry in prepared:
        record = entry.get("record")
        if (
            record is not None
            and not entry.get("is_syllabus")
            and selected_target is not None
            and selected_target.id != record.id
        ):
            document_service.link_material_to_syllabus(
                db,
                record,
                selected_target,
                unit_number if target is not None else None,
            )

    results: list[DocumentUploadResult] = []
    for entry in prepared:
        if "error" in entry:
            results.append(DocumentUploadResult(file_name=entry["name"], error=entry["error"]))
        else:
            results.append(
                DocumentUploadResult(
                    file_name=entry["name"],
                    document=_record_to_read(db, entry["record"]),
                )
            )
    return DocumentUploadResponse(uploaded=results)


@router.get("/", response_model=DocumentListResponse)
def get_documents(
    search: str = Query(default=""),
    class_id: str | None = Query(default=None),
    file_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    """Browse/search/filter/paginate the caller's own classes (List AC-01..05)."""
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status '{status}'.")
    rows, total = document_service.list_documents(
        db,
        user,
        search=search,
        class_id=class_id,
        file_type=file_type,
        status=status,
        page=page,
        page_size=page_size,
    )
    return DocumentListResponse(
        items=[_record_to_read(db, r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/classes/{class_id}/syllabus-units",
    response_model=TeacherSyllabusRead,
)
def teacher_syllabus_units(
    class_id: str,
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> TeacherSyllabusRead:
    """Draft-or-active syllabus units with per-unit materials for the teacher UI."""
    try:
        class_uuid = uuid.UUID(class_id)
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Class not found.")
    if class_uuid not in set(document_service.my_class_ids(db, user)):
        raise HTTPException(status_code=403, detail="Class is not assigned to you.")

    (
        record,
        is_draft,
        units,
        materials_by_unit,
        syllabus_materials,
    ) = document_service.get_teacher_syllabus_units(db, class_uuid)
    if record is None:
        return TeacherSyllabusRead(class_id=str(class_uuid), units=[])

    ready = document_service.ready_material_count(db, record)
    total = sum(len(items) for items in materials_by_unit.values()) + len(
        syllabus_materials
    )
    return TeacherSyllabusRead(
        class_id=str(class_uuid),
        document_id=str(record.id),
        file_name=record.file_name,
        status=record.status,
        is_draft=is_draft,
        ready_material_count=ready,
        total_material_count=total,
        can_approve=record.status == "pending" and ready > 0,
        units=[
            TeacherSyllabusUnitRead(
                unit_number=unit["unit_number"],
                unit_title=unit["unit_title"],
                description=unit["description"],
                content=unit["content"],
                materials=[
                    SyllabusMaterialRead(
                        id=str(material.id),
                        file_name=material.file_name,
                        status=material.status,
                        failure_reason=material.failure_reason,
                        version=material.version,
                        created_at=material.created_at,
                    )
                    for material in materials_by_unit.get(unit["unit_number"], [])
                ],
            )
            for unit in units
        ],
        syllabus_materials=[
            SyllabusMaterialRead(
                id=str(material.id),
                file_name=material.file_name,
                status=material.status,
                failure_reason=material.failure_reason,
                version=material.version,
                created_at=material.created_at,
            )
            for material in syllabus_materials
        ],
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> FileResponse:
    """AI-43 AC-02/AC-03: download the original file, trainer scope enforced."""
    record = _scoped_document(db, document_id, user)
    path = _stored_file(record)
    return FileResponse(
        path,
        media_type=record.mime_type or "application/octet-stream",
        filename=record.file_name,
        content_disposition_type="attachment",
    )


@router.get("/{document_id}/preview")
def preview_document(
    document_id: str,
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> FileResponse:
    """AI-43 AC-01/AC-03: inline preview for PDFs and images only."""
    record = _scoped_document(db, document_id, user)
    if not _is_previewable(record):
        raise HTTPException(
            status_code=415,
            detail="This file type cannot be previewed; download it instead.",
        )
    path = _stored_file(record)
    return FileResponse(
        path,
        media_type=record.mime_type,
        filename=record.file_name,
        content_disposition_type="inline",
    )


@router.post("/{document_id}/syllabus-link", response_model=DocumentRead)
def attach_document_to_syllabus(
    document_id: str,
    payload: AttachSyllabusMaterialRequest,
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> DocumentRead:
    """Attach an already-uploaded material to a draft/active syllabus unit.

    This is the explicit path for documents uploaded before the syllabus was
    created (e.g. an indexed PDF), without re-uploading the file.
    """
    record = _scoped_document(db, document_id, user)
    if record.status not in {
        document_service.STATUS_PENDING,
        document_service.STATUS_PROCESSING,
        document_service.STATUS_INDEXED,
    }:
        raise HTTPException(
            status_code=400,
            detail=f"A {record.status} document cannot be attached to a syllabus.",
        )
    if document_service.is_syllabus_record(db, record):
        raise HTTPException(
            status_code=400,
            detail="A syllabus file cannot be attached as unit material.",
        )
    resolved = document_service.validate_material_target(
        db,
        class_id=record.class_id,
        syllabus_document_id=payload.syllabus_document_id,
        unit_number=payload.unit_number,
        user=user,
    )
    if isinstance(resolved, str):
        raise HTTPException(status_code=400, detail=resolved)
    if resolved.id == record.id:
        raise HTTPException(
            status_code=400,
            detail="A syllabus file cannot be attached as its own material.",
        )
    try:
        record = document_service.link_material_to_syllabus(
            db,
            record,
            resolved,
            payload.unit_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _record_to_read(db, record)


@router.post("/{document_id}/approve", response_model=DocumentRead)
def approve_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(default=True),
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> DocumentRead:
    """Approve pending -> processing.

    AI-41 originally said trainer-only (TA gets 403). Under AI-27 RBAC,
    `require_trainer` admits `admin` too (superset); students still get 403
    from the dependency before reaching here.
    """
    record = document_service.get_document(db, document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if record.class_id not in document_service.my_class_ids(db, user):
        raise HTTPException(status_code=403, detail="Class is not assigned to you.")
    _require_uploader(record, user)
    try:
        record = document_service.approve_document(db, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    background_tasks.add_task(ingestion_service.process_document_in_background, str(record.id))
    return _record_to_read(db, record)


@router.post("/{document_id}/reject", response_model=DocumentRead)
def reject_document(
    document_id: str,
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> DocumentRead:
    """Reject a pending document within the trainer's assigned classes."""
    record = document_service.get_document(db, document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if record.class_id not in document_service.my_class_ids(db, user):
        raise HTTPException(status_code=403, detail="Class is not assigned to you.")
    _require_uploader(record, user)
    try:
        record = document_service.reject_document(db, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _record_to_read(db, record)


@router.post("/{document_id}/retry", response_model=DocumentRead)
def retry_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> DocumentRead:
    """Retry a failed document through the ingestion pipeline."""
    record = document_service.get_document(db, document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if record.class_id not in document_service.my_class_ids(db, user):
        raise HTTPException(status_code=403, detail="Class is not assigned to you.")
    _require_uploader(record, user)
    try:
        record = document_service.retry_document(db, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    background_tasks.add_task(ingestion_service.process_document_in_background, str(record.id))
    return _record_to_read(db, record)


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: str,
    confirm: bool = Query(default=False),
    user: User = Depends(require_trainer),
    db: Session = Depends(get_db),
) -> DocumentDeleteResponse:
    """Delete a document and purge its chunks from Qdrant (AI-39 AC-01/AC-04).

    Destructive, so it requires ``?confirm=true`` — the UI shows a confirm
    dialog first. Class scope matches approve: another trainer's document is
    never listed (AC-04) and is refused here by id too. When Qdrant cannot be
    reached for a vector-backed file, nothing is deleted and the API answers
    ``503`` so the outdated material can never keep answering (AC-02).
    """
    if not confirm:
        raise HTTPException(
            status_code=400, detail="Deletion requires confirmation (?confirm=true)."
        )
    record = document_service.get_document(db, document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if record.class_id not in document_service.my_class_ids(db, user):
        raise HTTPException(status_code=403, detail="Class is not assigned to you.")
    deleted_id, file_name, version = str(record.id), record.file_name, record.version
    try:
        purged = document_service.delete_document(db, record)
    except document_service.VectorPurgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return DocumentDeleteResponse(
        deleted=deleted_id, file_name=file_name, version=version, purged_chunks=purged
    )
