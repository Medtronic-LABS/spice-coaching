"""v3.3 source_document — canonical raw input artefact for the content pipeline.

Per Data Model v3.3 §3.1. Replaces the v1 `documents` table semantically (the old
`Document` model remains during the deprecation window). Carries authority_kind
(enum) + authority_label (free text) split, calibration calibration result for
Stage A, and outline_method tag for Stage B.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_service.db.base import Base


class SourceDocument(Base):
    __tablename__ = "source_document"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Groups versions of the same logical document (e.g. UHIS Q1 2026 + Q2 2026 share family).
    source_document_family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Enum stored as text for forward-compat: pdf | pptx | docx | image_set | video | transcript
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    # bn | en | bn_en_mixed
    primary_language: Mapped[str] = mapped_column(Text, nullable=False, default="bn")
    # Enum stored as text: official_training | clinical_guideline | supervisor_update | other
    authority_kind: Mapped[str] = mapped_column(Text, nullable=False, default="official_training")
    # Free-form, e.g. "UHIS RMNCH" / "BRAC SK FP&MH Manual" / "BRAC Bangladesh Supervisor Update April 2026"
    authority_label: Mapped[str] = mapped_column(Text, nullable=False)
    version_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    original_storage_path: Mapped[str] = mapped_column(Text, nullable=False)

    # Stage B output, populated after ingestion (markdown_parser | llm_fallback | failed).
    outline_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    outline_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Stage A calibration result per Pipeline v3.3 §4.4:
    # { "vision_pct": 0.55, "text_pct": 0.45, "sample_pages_evaluated": [3, 17, ...], "decision_at": "..." }
    extraction_calibration_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # ingesting | ingested | failed
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ingesting")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ingested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
