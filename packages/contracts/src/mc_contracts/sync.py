from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from mc_contracts.enums import ContentDomain
from mc_contracts.localized import LocaleConfig, LocalizedOptions, LocalizedString


class ConfigSyncBundle(BaseModel):
    """Configurable thresholds pushed to device for offline use."""

    thresholds: dict  # key → value_json
    locales: LocaleConfig
    server_time_utc: str


class ChatFaqItem(BaseModel):
    """One ranked frequent question mined from ``digital_help_used`` telemetry."""

    id: UUID
    question: LocalizedString
    occurrence_count: int
    rank: int
    last_seen_at: datetime | None = None


class ChatFaqsSyncBundle(BaseModel):
    """Frequent chat questions for on-device suggestion chips."""

    faqs: list[ChatFaqItem] = Field(default_factory=list)
    computed_at: datetime | None = None
    server_time_utc: str


class ModuleQuizQuestionPayload(BaseModel):
    id: UUID
    question_order: int | None
    question: LocalizedString
    case_setup: LocalizedString | None = None
    options: LocalizedOptions
    correct_indices: list[int]
    explanation: LocalizedString | None = None
    difficulty: str


class SourceDocumentSyncPayload(BaseModel):
    source_document_id: UUID
    title: str
    source_type: str
    primary_language: str
    content_domain: str
    version_label: str | None = None
    publication_date: date | None = None
    original_filename: str | None = None
    storage_path: str
    thumbnail_storage_path: str | None = None
    has_thumbnail: bool = False


class ModuleSyncPayload(BaseModel):
    """Published module payload for device sync (cards + quiz).

    Each card dict may include ``source_block_ids`` (when pipeline-drafted) and
    a server-enriched ``source_pages`` list (``CardSourcePageRef`` shape from
    ``mc_contracts.modules``). Presign fields on ``source_pages`` are null
    in the modules bundle; published document URLs are available via
    ``GET /sync/source-documents``.
    """

    id: UUID
    module_family_id: UUID
    version: int
    title: LocalizedString
    description: LocalizedString | None = None
    domain: str
    sub_domain: str | None
    module_type: str
    # Single content-domain tag for Learning Library / Practice Zone (Clinical | Digital | Operational).
    content_domain: ContentDomain = ContentDomain.CLINICAL
    tenant_id: int
    estimated_minutes: int
    difficulty_level: str
    pass_threshold_override: float | None
    clinically_reviewed: bool
    published_at: datetime | None
    updated_at: datetime
    source_documents: list[SourceDocumentSyncPayload] = Field(default_factory=list)
    has_thumbnail: bool = False
    thumbnail_storage_path: str | None = None
    thumbnail_presigned_url: str | None = None
    thumbnail_presigned_expires_seconds: int | None = None
    search_metadata: dict[str, Any] | None = None
    primary_gap_id: UUID | None = None
    behavioural_gap_ids: list[UUID] = Field(default_factory=list)
    cards: list[dict[str, Any]]
    quiz: list[ModuleQuizQuestionPayload]


class ModuleFamilySyncPayload(BaseModel):
    id: UUID
    module_code: str
    created_at: datetime
    created_by: int | None
    current_published_module_id: UUID | None


class AssignedModulePayload(BaseModel):
    module_id: UUID
    assigned_at: datetime


class VideoProgressPayload(BaseModel):
    """Current watch progress for a single assigned video."""

    source_document_id: UUID
    last_position_ms: int
    percent_watched: float
    completed: bool
    last_watched_at: datetime


class VideoProgressSyncBundle(BaseModel):
    """Delta watch progress for videos still assigned to the authenticated CHW."""

    videos: list[VideoProgressPayload] = Field(default_factory=list)
    server_time_utc: str


class RequestedModulePayload(BaseModel):
    """One CHW training request for offline history on the device."""

    request_id: UUID
    module_id: UUID | None = None
    requested_module_name: str | None = None
    reason: str | None = None
    submitted_at: datetime


class ModulesSyncBundle(BaseModel):
    modules: list[ModuleSyncPayload]
    module_families: list[ModuleFamilySyncPayload]
    assigned_module_ids: list[AssignedModulePayload] = Field(default_factory=list)
    requested_modules: list[RequestedModulePayload] = Field(default_factory=list)
    server_time_utc: str


class SourceDocumentSyncDownloadPayload(BaseModel):
    """Presigned download payload for one source document on device sync.

    Used for module-linked documents (``source_documents``) and for the CHW's
    direct ``document_assignment`` snapshot (``assigned_documents``).
    ``assigned_at`` is set only on assigned-document rows.
    """

    source_document_id: UUID
    source_type: str
    title: str | None = None
    description: str | None = None
    original_filename: str | None = None
    storage_path: str
    thumbnail_storage_path: str | None = None
    assigned_at: datetime | None = None
    duration_ms: int | None = None
    presigned_url: str | None = None
    presigned_expires_seconds: int | None = None
    thumbnail_presigned_url: str | None = None
    thumbnail_presigned_expires_seconds: int | None = None


class SourceDocumentsSyncBundle(BaseModel):
    """Presigned URLs for module-linked and assigned source documents."""

    source_documents: list[SourceDocumentSyncDownloadPayload] = Field(default_factory=list)
    assigned_documents: list[SourceDocumentSyncDownloadPayload] = Field(default_factory=list)
    server_time_utc: str


class TriggerDefinitionSyncPayload(BaseModel):
    id: UUID
    trigger_kind: str
    trigger_code: str
    description: str | None
    predicate_jsonb: dict[str, Any]
    predicate_schema_version: int
    status: str
    tenant_id: int
    created_at: datetime
    updated_at: datetime


class ModuleTriggerBindingSyncPayload(BaseModel):
    id: UUID
    trigger_definition_id: UUID
    module_id: UUID
    relationship: str
    priority_weight: int
    notes: str | None


class TriggersSyncBundle(BaseModel):
    triggers: list[TriggerDefinitionSyncPayload]
    bindings: list[ModuleTriggerBindingSyncPayload]
    server_time_utc: str


class BehaviouralGapSyncPayload(BaseModel):
    id: UUID
    gap_code: str
    description: str
    domain: str
    severity_default: str
    detection_rule_jsonb: dict[str, Any]
    updated_at: datetime


class CHWBehaviouralGapStateSyncPayload(BaseModel):
    chw_id: int
    behavioural_gap_id: UUID
    tenant_id: int
    severity_current: str
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    last_reinforced_at: datetime | None
    occurrence_count: int
    failed_attempts_count: int
    last_failed_attempt_at: datetime | None
    escalated_to_supervisor: bool
    status: str
    updated_at: datetime | None


class CHWQuizQuestionStateSyncPayload(BaseModel):
    chw_id: int
    quiz_id: UUID
    module_id: UUID
    tenant_id: int
    failed_attempts_count: int
    last_failed_attempt_at: datetime | None
    first_attempt_at: datetime | None
    last_attempt_at: datetime | None
    escalated_to_supervisor: bool
    status: str
    updated_at: datetime | None


class CHWModuleCompletionSyncPayload(BaseModel):
    chw_id: int
    module_family_id: UUID
    latest_completed_module_id: UUID | None
    latest_attempt_module_id: UUID | None
    completed_at: datetime | None
    latest_attempt_at: datetime | None
    latest_quiz_score: float | None
    latest_attempt_passed: bool
    attempts_since_last_pass: int
    reinforcement_due_at: datetime | None
    tenant_id: int


class CHWModulePartialCompletionSyncPayload(BaseModel):
    chw_id: int
    module_id: UUID
    module_family_id: UUID
    incomplete_quiz_ids: list[UUID]
    tenant_id: int


class GapsSyncBundle(BaseModel):
    behavioural_gaps: list[BehaviouralGapSyncPayload]
    chw_behavioural_gap_states: list[CHWBehaviouralGapStateSyncPayload]
    chw_quiz_question_states: list[CHWQuizQuestionStateSyncPayload] = Field(default_factory=list)
    chw_module_completions: list[CHWModuleCompletionSyncPayload]
    chw_module_partial_completions: list[CHWModulePartialCompletionSyncPayload] = Field(default_factory=list)
    server_time_utc: str
    total_points: int = 0


class SourceDocumentPresignedUrlPayload(BaseModel):
    source_document_id: UUID
    storage_path: str
    presigned_url: str
    expires_seconds: int


class SourceDocumentsPresignResponse(BaseModel):
    urls: list[SourceDocumentPresignedUrlPayload]
    missing_ids: list[UUID]
    server_time_utc: str


class SourceDocumentThumbnailPresignedUrlPayload(BaseModel):
    source_document_id: UUID
    storage_path: str
    presigned_url: str
    expires_seconds: int


class SourceDocumentThumbnailsPresignResponse(BaseModel):
    urls: list[SourceDocumentThumbnailPresignedUrlPayload]
    missing_ids: list[UUID]
    server_time_utc: str


_MAX_STORAGE_PATHS_PER_BATCH = 50


class StoragePathsPresignRequest(BaseModel):
    storage_paths: list[str] = Field(..., min_length=1, max_length=_MAX_STORAGE_PATHS_PER_BATCH)


class StoragePathPresignedUrlPayload(BaseModel):
    storage_path: str
    presigned_url: str
    expires_seconds: int


class StoragePathsPresignResponse(BaseModel):
    urls: list[StoragePathPresignedUrlPayload]
    missing_paths: list[str]
    server_time_utc: str


class AvailableBadgePayload(BaseModel):
    id: UUID
    name: str
    domain: str
    image_storage_path: str
    image_presigned_url: str | None = None
    image_presigned_expires_seconds: int | None = None
    sequence: int | None = None
    module_ids: list[UUID] = Field(default_factory=list)


class EarnedBadgePayload(BaseModel):
    id: UUID
    name: str
    domain: str
    image_storage_path: str
    image_presigned_url: str | None = None
    image_presigned_expires_seconds: int | None = None
    sequence: int | None = None
    module_ids: list[UUID] = Field(default_factory=list)
    earned_at: datetime


class BadgesSyncBundle(BaseModel):
    available_badges: list[AvailableBadgePayload] = Field(default_factory=list)
    earned_badges: list[EarnedBadgePayload] = Field(default_factory=list)
    server_time_utc: str
