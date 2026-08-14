"""Admin source document catalog — list + post-upload metadata updates."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from mc_contracts.enums import SourceDocumentType
from mc_contracts.errors import ErrorCode
from mc_contracts.source_documents import (
    SourceDocumentActorRef,
    SourceDocumentListItem,
    SourceDocumentListResponse,
    SourceDocumentMetadataUpdate,
    SourceDocumentSummary,
)
from mc_foundation.objectstore import ObjectStore
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_user import resolve_spice_user_id
from platform_service.db.models.hierarchy_user import HierarchyUser
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.repositories.document_assignment_repository import (
    DocumentAssignmentRepository,
)
from platform_service.db.repositories.hierarchy_repository import HierarchyRepository
from platform_service.db.repositories.source_repository import (
    DEFAULT_SOURCE_DOCUMENT_SORT_BY,
    DEFAULT_SOURCE_DOCUMENT_SORT_DIR,
    SOURCE_DOCUMENT_SORT_DIRS,
    SOURCE_DOCUMENT_SORT_KEYS,
    SourceRepository,
)
from platform_service.deps import get_db, get_object_storage_client
from platform_service.services.source_thumbnail_service import SourceThumbnailService

router = APIRouter(prefix="/admin", tags=["admin-source-documents"])

VALID_SOURCE_DOCUMENT_STATUSES = frozenset({"uploaded", "ingesting", "ingested", "failed", "retired"})
VALID_SOURCE_DOCUMENT_TYPES = frozenset(e.value for e in SourceDocumentType)
_MAX_THUMBNAIL_BYTES = 5 * 1024 * 1024


def _summary_from_document(doc: SourceDocument) -> SourceDocumentSummary:
    return SourceDocumentSummary(
        id=doc.id,
        title=doc.title,
        source_type=doc.source_type,
        status=doc.status,
        content_domain=doc.content_domain,
        stored_path=doc.original_storage_path,
        original_filename=doc.original_filename,
        description=doc.description,
        thumbnail_storage_path=doc.thumbnail_storage_path,
        duration_ms=doc.duration_ms,
        uploaded_date=doc.uploaded_date,
        ingested_at=doc.ingested_at,
        updated_at=doc.updated_at,
    )


def _actor_ref(user_id: int | None, users_by_id: dict[int, HierarchyUser]) -> SourceDocumentActorRef | None:
    if user_id is None:
        return None
    user = users_by_id.get(user_id)
    if user is None:
        return None
    return SourceDocumentActorRef(id=user.id, name=user.name)


def _list_item_from_document(
    doc: SourceDocument,
    *,
    users_by_id: dict[int, HierarchyUser],
    assigned_ids: set[UUID],
) -> SourceDocumentListItem:
    return SourceDocumentListItem(
        id=doc.id,
        title=doc.title,
        source_type=doc.source_type,
        status=doc.status,
        content_domain=doc.content_domain,
        stored_path=doc.original_storage_path,
        original_filename=doc.original_filename,
        description=doc.description,
        thumbnail_storage_path=doc.thumbnail_storage_path,
        duration_ms=doc.duration_ms,
        uploaded_date=doc.uploaded_date,
        ingested_at=doc.ingested_at,
        updated_at=doc.updated_at,
        uploaded_by=_actor_ref(doc.uploaded_by, users_by_id),
        updated_by=_actor_ref(doc.updated_by, users_by_id),
        ingested_by=_actor_ref(doc.ingested_by, users_by_id),
        assigned=doc.id in assigned_ids,
    )


def _normalize_csv_query_values(raw: list[str] | None) -> list[str] | None:
    """Accept repeated params and/or comma-separated values; dedupe, preserve order."""
    if not raw:
        return None
    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        for part in item.split(","):
            value = part.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            values.append(value)
    return values or None


@router.get("/source-documents", response_model=SourceDocumentListResponse)
async def list_source_documents(
    status: list[str] | None = Query(
        None,
        description=(
            "Optional filter; repeat and/or comma-separate: "
            "uploaded | ingesting | ingested | failed | retired "
            "(omit for all non-retired statuses; e.g. status=uploaded&status=ingested "
            "or status=uploaded,ingested; use status=retired to list retired only)"
        ),
    ),
    source_type: list[str] | None = Query(
        None,
        description=(
            "Optional filter; repeat and/or comma-separate: "
            "pdf | pptx | docx | audio | video "
            "(e.g. source_type=video&source_type=audio or source_type=video,audio)"
        ),
    ),
    sync_published_visible: bool | None = Query(
        None,
        description=(
            "Optional filter on knowledge vs ingest documents: "
            "true = knowledge (sync_published_visible), false = ingest; "
            "omit for both"
        ),
    ),
    q: str | None = Query(
        None,
        description="Case-insensitive substring match on original_filename or title",
    ),
    uploaded_from: datetime | None = Query(
        None,
        description="Optional inclusive start datetime filter on uploaded_date (ISO-8601 UTC)",
    ),
    uploaded_to: datetime | None = Query(
        None,
        description="Optional inclusive end datetime filter on uploaded_date (ISO-8601 UTC)",
    ),
    uploaded_by: list[str] | None = Query(
        None,
        description=(
            "Optional filter by uploader hierarchy user id(s); repeat and/or comma-separate "
            "(e.g. uploaded_by=101&uploaded_by=102 or uploaded_by=101,102)"
        ),
    ),
    assigned: bool | None = Query(
        None,
        description=(
            "Optional filter on document assignment: "
            "true = has at least one document_assignment row; "
            "false = unassigned; omit for both"
        ),
    ),
    sort_by: str = Query(
        DEFAULT_SOURCE_DOCUMENT_SORT_BY,
        description=(
            "ingested_at | uploaded_date | title | source_type | status | content_domain | original_filename"
        ),
    ),
    sort_dir: str = Query(
        DEFAULT_SOURCE_DOCUMENT_SORT_DIR,
        description="asc | desc",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> SourceDocumentListResponse:
    if uploaded_from is not None and uploaded_to is not None and uploaded_from > uploaded_to:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            "uploaded_from must be on or before uploaded_to",
            status=422,
        )
    statuses = _normalize_csv_query_values(status)
    if statuses is not None:
        invalid_statuses = [s for s in statuses if s not in VALID_SOURCE_DOCUMENT_STATUSES]
        if invalid_statuses:
            raise AppError(
                ErrorCode.INVALID_QUERY.value,
                (
                    f"status must be one of: {', '.join(sorted(VALID_SOURCE_DOCUMENT_STATUSES))}; "
                    f"got invalid: {', '.join(invalid_statuses)}"
                ),
                status=422,
            )
    source_types = _normalize_csv_query_values(source_type)
    if source_types is not None:
        invalid = [t for t in source_types if t not in VALID_SOURCE_DOCUMENT_TYPES]
        if invalid:
            raise AppError(
                ErrorCode.INVALID_QUERY.value,
                (
                    f"source_type must be one of: {', '.join(sorted(VALID_SOURCE_DOCUMENT_TYPES))}; "
                    f"got invalid: {', '.join(invalid)}"
                ),
                status=422,
            )
    uploaded_by_raw = _normalize_csv_query_values(uploaded_by)
    uploaded_by_ids: list[int] | None = None
    if uploaded_by_raw is not None:
        uploaded_by_ids = []
        invalid_uploaded_by: list[str] = []
        for token in uploaded_by_raw:
            try:
                uploaded_by_ids.append(int(token))
            except ValueError:
                invalid_uploaded_by.append(token)
        if invalid_uploaded_by:
            raise AppError(
                ErrorCode.INVALID_QUERY.value,
                f"uploaded_by must be integer user id(s); got invalid: {', '.join(invalid_uploaded_by)}",
                status=422,
            )
    if sort_by not in SOURCE_DOCUMENT_SORT_KEYS:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"sort_by must be one of: {', '.join(sorted(SOURCE_DOCUMENT_SORT_KEYS))}",
            status=422,
        )
    if sort_dir not in SOURCE_DOCUMENT_SORT_DIRS:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"sort_dir must be one of: {', '.join(sorted(SOURCE_DOCUMENT_SORT_DIRS))}",
            status=422,
        )
    filename_query = q.strip() if q and q.strip() else None
    repo = SourceRepository(session)
    list_filters = {
        "statuses": statuses,
        "source_types": source_types,
        "filename_query": filename_query,
        "sync_published_visible": sync_published_visible,
        "uploaded_from": uploaded_from,
        "uploaded_to": uploaded_to,
        "uploaded_by_ids": uploaded_by_ids,
        "assigned": assigned,
    }
    total_source_documents = await repo.count_source_documents(**list_filters)
    docs = await repo.list_source_documents(
        **list_filters,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    actor_ids = {
        uid for doc in docs for uid in (doc.uploaded_by, doc.updated_by, doc.ingested_by) if uid is not None
    }
    users_by_id = await HierarchyRepository(session).get_users_by_ids(list(actor_ids))
    assigned_ids = await DocumentAssignmentRepository(session).source_document_ids_with_assignments(
        [doc.id for doc in docs]
    )
    total_pages = (total_source_documents + limit - 1) // limit if total_source_documents > 0 else 0
    return SourceDocumentListResponse(
        source_documents=[
            _list_item_from_document(doc, users_by_id=users_by_id, assigned_ids=assigned_ids) for doc in docs
        ],
        total_source_documents=total_source_documents,
        total_pages=total_pages,
        limit=limit,
        offset=offset,
    )


@router.patch("/source-documents/{source_document_id}", response_model=SourceDocumentSummary)
async def update_source_document_metadata(
    source_document_id: UUID,
    body: SourceDocumentMetadataUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SourceDocumentSummary:
    """Update title and/or description without re-ingest."""
    if body.title is None and "description" not in body.model_fields_set:
        raise HTTPException(status_code=422, detail="at least one of title or description is required")
    if body.title is not None and not body.title.strip():
        raise HTTPException(status_code=422, detail="title must be a non-empty string")

    repo = SourceRepository(session)
    update_description = "description" in body.model_fields_set
    description_value = body.description
    if update_description and description_value is not None:
        description_value = description_value.strip() or None

    doc = await repo.update_metadata(
        source_document_id,
        title=body.title.strip() if body.title is not None else None,
        description=description_value,
        update_description=update_description,
        updated_by=resolve_spice_user_id(request),
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="source document not found")
    await session.commit()
    # Re-load server-generated columns (e.g. updated_at onupdate) before sync DTO mapping.
    await session.refresh(doc)
    return _summary_from_document(doc)


@router.put("/source-documents/{source_document_id}/thumbnail", response_model=SourceDocumentSummary)
async def upload_source_document_thumbnail(
    source_document_id: UUID,
    request: Request,
    file: UploadFile = File(..., description="Thumbnail image (PNG, JPEG, or WebP)"),
    session: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
) -> SourceDocumentSummary:
    """Replace the source document thumbnail without re-ingest."""
    content_type = file.content_type or ""
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="thumbnail file is empty")
    if len(image_bytes) > _MAX_THUMBNAIL_BYTES:
        raise HTTPException(status_code=422, detail="thumbnail exceeds 5 MB limit")

    thumb_svc = SourceThumbnailService(session, storage=storage)
    try:
        await thumb_svc.store_custom_thumbnail(
            source_document_id=source_document_id,
            image_bytes=image_bytes,
            content_type=content_type,
            updated_by=resolve_spice_user_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    doc = await SourceRepository(session).get_source_document(source_document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="source document not found")
    return _summary_from_document(doc)
