"""Source document catalog API contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from mc_contracts.actors import UserActorRef


class SourceDocumentSummary(BaseModel):
    """List-row response for admin source document catalog (ingest dropdowns)."""

    id: UUID
    title: str
    source_type: str
    status: str
    content_domain: str
    stored_path: str
    original_filename: str | None = None
    description: str | None = None
    thumbnail_storage_path: str | None = None
    duration_ms: int | None = None
    uploaded_date: datetime
    ingested_at: datetime
    updated_at: datetime


class SourceDocumentListItem(SourceDocumentSummary):
    """Admin catalog row with actor + assignment enrichment."""

    uploaded_by: UserActorRef | None = None
    updated_by: UserActorRef | None = None
    ingested_by: UserActorRef | None = None
    assigned: bool = False


class SourceDocumentMetadataUpdate(BaseModel):
    """Partial update for source document title / description (no re-ingest)."""

    title: str | None = None
    description: str | None = None


class SourceDocumentListResponse(BaseModel):
    """Paginated admin source document list envelope for ``GET /admin/source-documents``."""

    source_documents: list[SourceDocumentListItem]
    total_source_documents: int
    total_pages: int
    limit: int
    offset: int
