"""source_document — canonical raw input artefact for the content pipeline.

See `docs/content-administration/ingest-pipeline.md`. Carries content_domain,
calibration result for extract, and outline_method tag. Ingest-time
config (assessment_mode, instructions, cardinality) lives on ingest_batch.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_service.db.base import Base
from platform_service.db.models.mixins import TenantMixin


class SourceDocument(TenantMixin, Base):
    __tablename__ = "source_document"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Groups versions of the same logical document (e.g. UHIS Q1 2026 + Q2 2026 share family).
    source_document_family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional admin-provided summary (set at ingest or via PATCH; never drives the pipeline).
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Enum stored as text for forward-compat: pdf | pptx | docx | image_set | video | transcript
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    # bn | en | bn_en_mixed
    primary_language: Mapped[str] = mapped_column(Text, nullable=False, default="bn")
    # Enum stored as text: clinical | digital | operational
    content_domain: Mapped[str] = mapped_column(Text, nullable=False, default="clinical")
    version_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    original_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    # Object-storage path to ingest thumbnail PNG ({bucket}/ingest/thumbnails/{id}.png).
    thumbnail_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Audio/video length in milliseconds; null for documents and when ffprobe fails.
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Optional audit / dedup (populated by ingest when bytes are available).
    content_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Spice / hierarchy user id (see users.id); no hard FK — soft-join at list time.
    uploaded_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Stage B output, populated after ingestion (markdown_parser | llm_fallback | failed).
    outline_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    outline_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Stage A calibration result see `docs/content-administration/ingest-pipeline.md`:
    # { "vision_pct": 0.55, "text_pct": 0.45, "sample_pages_evaluated": [3, 17, ...], "decision_at": "..." }
    extraction_calibration_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # When true, knowledge-catalog docs (admin sync_published_visible filtering).
    # Device sync inclusion is via published-module links / document_assignment
    # (GET /sync/source-documents), not this flag.
    sync_published_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # uploaded | ingesting | ingested | partially_succeeded | failed | retired
    status: Mapped[str] = mapped_column(Text, nullable=False, default="uploaded")
    uploaded_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Spice / hierarchy user id (see users.id); no hard FK — soft-join at list time.
    ingested_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
