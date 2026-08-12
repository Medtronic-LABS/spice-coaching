"""Admin knowledge document upload, uploader list, and soft-delete routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from mc_contracts.knowledge import (
    KnowledgeUploadedSource,
    KnowledgeUploadersResponse,
    KnowledgeUploadResponse,
)
from mc_foundation.objectstore import ObjectStore
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_user import (
    get_selected_tenant_id,
    resolve_spice_actor,
    resolve_spice_user_id,
)
from platform_service.deps import get_db, get_object_storage_client
from platform_service.services.knowledge_upload_service import KnowledgeUploadService

router = APIRouter(
    prefix="/admin/knowledge",
    tags=["admin-knowledge"],
)


@router.post("/upload", status_code=201, response_model=KnowledgeUploadResponse)
async def upload_knowledge_document(
    request: Request,
    file: UploadFile = File(..., description="PDF file to publish as knowledge source document(s)"),
    title: str | None = Form(
        None,
        description="Optional title for whole-file mode; defaults to the PDF basename stem",
    ),
    thumbnail_storage_path: str | None = Form(
        None,
        description=(
            "Optional thumbnail storage path from a prior POST /admin/files upload "
            "(whole-file mode only; ignored when splits is non-empty)"
        ),
    ),
    splits: str | None = Form(
        None,
        description=(
            "Optional JSON array of splits: "
            "[{start_page, end_page, title, thumbnail_storage_path?}]. "
            "Omit or [] to keep the whole file as one source document."
        ),
    ),
    override_duplicates: bool = Form(
        False,
        description=(
            "When true, re-upload even if any produced artifact's content_sha256 matches an "
            "already-uploaded or already-ingested source_document in the selected tenant."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
) -> KnowledgeUploadResponse:
    """Upload a PDF as one or more published-visible source documents (no ingest pipeline)."""
    actor = resolve_spice_actor(request)
    tenant_id = get_selected_tenant_id(request)
    results = await KnowledgeUploadService(db, storage).upload(
        file=file,
        actor=actor,
        uploaded_by_user_id=resolve_spice_user_id(request),
        title=title,
        thumbnail_storage_path=thumbnail_storage_path,
        splits_json=splits,
        tenant_id=tenant_id,
        override_duplicates=override_duplicates,
    )
    await db.commit()
    return KnowledgeUploadResponse(
        sources=[
            KnowledgeUploadedSource(
                source_document_id=result.source_document_id,
                title=result.title,
                stored_path=result.stored_path,
                thumbnail_storage_path=result.thumbnail_storage_path,
                start_page=result.start_page,
                end_page=result.end_page,
            )
            for result in results
        ],
    )


@router.get("/uploaders", response_model=KnowledgeUploadersResponse)
async def list_knowledge_uploaders(
    request: Request,
    db: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
) -> KnowledgeUploadersResponse:
    """List distinct hierarchy users who uploaded active knowledge documents in the selected tenant."""
    tenant_id = get_selected_tenant_id(request)
    uploaders = await KnowledgeUploadService(db, storage).list_uploaders(tenant_id=tenant_id)
    return KnowledgeUploadersResponse(uploaders=uploaders)


@router.delete("/{source_document_id}", status_code=204)
async def retire_knowledge_document(
    source_document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
) -> Response:
    """Soft-delete a knowledge source document (``status='retired'``)."""
    await KnowledgeUploadService(db, storage).retire(
        source_document_id,
        updated_by=resolve_spice_user_id(request),
    )
    await db.commit()
    return Response(status_code=204)
