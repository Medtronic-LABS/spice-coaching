"""Module API contracts — platform → admin dashboard."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from mc_contracts.enums import ContentDomain
from mc_contracts.localized import LocalizedOptions, LocalizedString
from mc_contracts.source_documents import SourceDocumentActorRef


class ModuleLifecycleActionRequest(BaseModel):
    actor_id: UUID | None = None
    reason: str | None = None


class ModuleLifecycleStatePayload(BaseModel):
    module_id: UUID
    module_family_id: UUID
    lifecycle_status: str
    activated_at: datetime | None
    deactivated_at: datetime | None


class ModuleSummary(BaseModel):
    """List-row response. Keeps the payload light; full content via GET /modules/:id."""

    id: UUID
    module_family_id: UUID
    version: int
    title: LocalizedString
    description: LocalizedString | None = None
    domain: str
    content_domain: ContentDomain | None = None
    module_type: str
    lifecycle_status: str
    clinically_reviewed: bool
    has_visibility_window: bool
    card_count: int
    quiz_count: int
    estimated_minutes: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None
    # Quality flags written by Stage 2 / Stage 2-draft (e.g.
    # `insufficient_source_filter`, drafter `insufficient_reason`). Surfaced
    # so the dashboard can build a "needs attention" view; presence of any
    # flag does NOT block publish.
    quality_flags: dict[str, Any] | None
    # LLM-generated bilingual keywords, search phrases, and topic tags for retrieval.
    search_metadata: dict[str, Any] | None = None
    chatbot_faqs_only: bool = False
    thumbnail_storage_path: str | None = None
    thumbnail_presigned_url: str | None = None
    thumbnail_presigned_expires_seconds: int | None = None
    # Per-module source document linkage for dashboard document filters.
    source_document_ids: list[str] | None = None
    # Dual-path merge links (null when not part of a merge pair).
    merge_secondary_module_id: UUID | None = None
    merge_primary_module_id: UUID | None = None
    merge_source_module_id: UUID | None = None
    created_by: SourceDocumentActorRef | None = None
    published_by: SourceDocumentActorRef | None = None
    deactivated_by: SourceDocumentActorRef | None = None
    activated_by: SourceDocumentActorRef | None = None


class ModuleListResponse(BaseModel):
    """Paginated admin module list envelope for ``GET /admin/modules``."""

    modules: list[ModuleSummary]
    total_modules: int
    total_pages: int
    limit: int
    offset: int


class ModuleSourceDocumentRef(BaseModel):
    """Linked source document with optional object-storage presigned GET URL."""

    source_document_id: UUID
    presigned_url: str | None = None
    presigned_expires_seconds: int | None = None
    thumbnail_storage_path: str | None = None
    thumbnail_presigned_url: str | None = None
    thumbnail_presigned_expires_seconds: int | None = None


class CardSourcePageRef(BaseModel):
    """One source page cited by a module card (via ``source_block_ids``)."""

    source_document_id: UUID
    page_number: int
    start_ms: int | None = Field(
        default=None,
        description="AV chunk start time in milliseconds; null for PDF/DOCX/PPTX pages.",
    )
    end_ms: int | None = Field(
        default=None,
        description="AV chunk end time in milliseconds; null for PDF/DOCX/PPTX pages.",
    )
    presigned_url: str | None = Field(
        default=None,
        description="Presigned GET URL for the source document with ``#page=N`` for PDF deep-linking.",
    )
    presigned_expires_seconds: int | None = None


class QuizQuestionPayload(BaseModel):
    id: UUID
    question_order: int | None
    question: LocalizedString
    case_setup: LocalizedString | None = None
    options: LocalizedOptions
    correct_indices: list[int]
    explanation: LocalizedString | None = None
    difficulty: str


class ModuleDetail(ModuleSummary):
    """Full module: shell + cards + quiz + attachment refs (no presigned URLs on file refs).

    Each card dict includes ``card_family_id``, may include ``source_block_ids`` (when
    pipeline-drafted) and a server-enriched ``source_pages`` list (``CardSourcePageRef`` shape).
    """

    cards: list[dict[str, Any]]
    attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Module-level attachments from module_json; presign via GET /admin/files/presigned-url on demand",
    )
    quiz: list[QuizQuestionPayload]
    sub_domain: str | None
    estimated_minutes: int
    difficulty_level: str
    pass_threshold_override: float | None
    visibility_window_lower: datetime | None
    visibility_window_upper: datetime | None
    source_documents: list[ModuleSourceDocumentRef] = Field(default_factory=list)
    primary_gap_id: UUID | None = None
    behavioural_gap_ids: list[UUID] = Field(default_factory=list)


class QuizQuestionEditRequest(BaseModel):
    id: str | None = None
    question_order: int | None = None
    question: LocalizedString | None = None
    case_setup: LocalizedString | None = None
    options: LocalizedOptions
    correct_indices: list[int]
    explanation: LocalizedString | None = None
    difficulty: str = "moderate"


class ModuleEditRequest(BaseModel):
    """Edit a module tip; creates a new draft version unless the body is a complete
    content snapshot that matches the current tip (idempotent no-op).

    A complete snapshot requires ``title``, ``description``, ``module_json``,
    ``thumbnail_storage_path``, and quiz either as top-level ``quiz`` or nested under
    ``module_json.quiz``. Gap ids are ignored for equality.
    Omitted or unchanged ``chatbot_faqs_only`` does not break the no-op; an explicit
    different value still creates a new draft version. Omitted content fields always
    version-bump.
    """

    expected_version: int = Field(
        ...,
        ge=1,
        description=(
            "Version of the module row being edited; must match the server tip "
            "or the request fails with 409 module_version_conflict"
        ),
    )
    title: LocalizedString | None = None
    description: LocalizedString | None = None
    module_json: dict[str, Any] | None = None
    quiz: list[QuizQuestionEditRequest] | None = None
    behavioural_gap_ids: list[UUID] | None = Field(
        default=None,
        description="When set, replaces all gap links on the new module version",
    )
    primary_gap_id: UUID | None = Field(
        default=None,
        description="Primary gap for quiz state; must be in behavioural_gap_ids when both are set",
    )
    thumbnail_storage_path: str | None = Field(
        default=None,
        description=(
            "Object storage path to module preview image. Omit to copy forward on version bump; "
            "send null to clear; send a path to set or replace (upload via POST /admin/files)."
        ),
    )
    chatbot_faqs_only: bool | None = Field(
        default=None,
        description=(
            "When set, updates this module version flag. True restricts the module to "
            "chatbot knowledge retrieval only (no CHW training workflows)."
        ),
    )
    content_domain: ContentDomain | None = Field(
        default=None,
        description="Learning Library content domain for this module version.",
    )


class ModuleCreateRequest(BaseModel):
    title: LocalizedString
    description: LocalizedString | None = None
    domain: str = "clinical"
    sub_domain: str | None = None
    content_domain: ContentDomain = ContentDomain.CLINICAL
    module_type: str = "refresher"
    estimated_minutes: int = 10
    difficulty_level: str = "moderate"
    module_json: dict[str, Any] | None = None
    quiz: list[QuizQuestionEditRequest] | None = None
    behavioural_gap_ids: list[UUID] | None = None
    primary_gap_id: UUID | None = None
    chatbot_faqs_only: bool = Field(
        default=False,
        description=(
            "When true, the module is for chatbot FAQ/RAG knowledge only and is excluded "
            "from CHW training, assignments, and refresher workflows."
        ),
    )


class ModuleAttachmentKind(str, enum.Enum):
    FILE = "file"
    YOUTUBE = "youtube"


class ModuleMediaKind(str, enum.Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    PDF = "pdf"


class CardMediaAnchor(BaseModel):
    """Provenance for an ingest-assigned card image (additive; clients may ignore)."""

    field: Literal["body", "title"] = "body"
    strategy: Literal["source_proximity", "hybrid"] = "hybrid"
    source_page_number: int | None = None
    nearby_block_ids: list[str] = Field(default_factory=list)
    start_ms: int | None = Field(
        default=None,
        description="Video frame start timecode when media came from an AV source.",
    )
    end_ms: int | None = Field(
        default=None,
        description="Video frame end timecode when media came from an AV source.",
    )


class CardMediaItem(BaseModel):
    """Structured card media from document figure assignment (not manual attachments)."""

    source_image_id: str = Field(..., description="UUID of source_image row")
    storage_path: str = Field(..., description="Full bucket/path in object storage")
    content_type: str
    alt: str | None = None
    caption: str | None = None
    anchor: CardMediaAnchor | None = None


class ModuleAttachmentFileRef(BaseModel):
    """Reference to a file already stored in object storage."""

    kind: Literal["file"] = "file"
    attachment_id: str = Field(..., description="UUID string; stable within a module version")
    label: str | None = None
    sort_order: int = 0
    storage_path: str = Field(..., description="Full bucket/path from upload response")
    object_name: str = Field(..., description="Object key within the bucket, e.g. media/{uuid}_file.pdf")
    content_type: str
    original_filename: str | None = None
    media_kind: ModuleMediaKind


class ModuleAttachmentYoutubeRef(BaseModel):
    """External YouTube link (no object-storage object)."""

    kind: Literal["youtube"] = "youtube"
    attachment_id: str = Field(..., description="UUID string; stable within a module version")
    label: str | None = None
    sort_order: int = 0
    youtube_url: str = Field(..., description="Canonical watch URL")
    youtube_video_id: str | None = Field(
        None,
        description="Denormalized video id for embed UIs",
    )


ModuleAttachmentRef = Annotated[
    ModuleAttachmentFileRef | ModuleAttachmentYoutubeRef,
    Field(discriminator="kind"),
]
