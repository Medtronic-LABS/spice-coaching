"""ModuleCard — presentation slice linked directly to one module version.

Cards are relational (like ``module_quiz_question``) so telemetry, quiz
linkage, and per-card enrichment can use stable ``card_family_id`` values.
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_service.config import get_settings
from platform_service.db.base import Base

_EMBEDDING_DIM = get_settings().embedding_dimension


class ModuleCard(Base):
    __tablename__ = "module_card"
    __table_args__ = (
        UniqueConstraint(
            "card_family_id",
            "card_version",
            name="uq_module_card_family_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("module.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    card_order: Mapped[int] = mapped_column(Integer, nullable=False)
    card_family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    card_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    title_localized: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    body_localized: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    previous_practice_localized: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    current_practice_localized: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    rationale_for_change_localized: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    next_action_localized: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)

    thresholds_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_block_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    figure_ref_block_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    search_metadata_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    attachments_jsonb: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    # Additive card media from ingest figure assignment (not manual attachments).
    media_jsonb: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    field_flags_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Local EmbeddingGemma vector for device-parity / offline retrieval eval.
    # Written by bin/backfill_module_card_local_embeddings.py; not used in production RAG.
    local_embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
