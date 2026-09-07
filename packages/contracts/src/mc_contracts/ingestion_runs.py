"""Ingestion run API contracts — platform → admin dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from mc_contracts.actors import UserActorRef


class IngestionRunSummary(BaseModel):
    id: UUID
    source_document_id: UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    error: dict[str, Any] | None
    # Prefer original_filename when present; otherwise source_document.title.
    document_label: str = ""
    # Frozen at run completion (after post-publish). Distinct primary module_id
    # from this run's card_draft steps plus same-batch shared modules that list
    # this source_document; dual-path review_pending secondaries are excluded.
    # Missing snapshot rows (e.g. historical runs) present as 0.
    generated_module_count: int = 0
    generated_card_count: int = 0
    generated_quiz_count: int = 0
    ingested_by: UserActorRef | None = None


class IngestionRunListResponse(BaseModel):
    """Paginated admin ingestion-run list envelope for ``GET /admin/ingestion-runs``."""

    runs: list[IngestionRunSummary]
    total_runs: int
    total_pages: int
    limit: int
    offset: int


class IngestionRunCandidatePayload(BaseModel):
    candidate_id: UUID
    proposed_title: str
    domain: str | None = None
    behavioural_gap_code: str | None
    proposed_module_type: str | None
    estimated_card_count: int | None
    estimated_quiz_count: int | None
    quality_flags: dict[str, Any] | None = None
    ingestion_instruction_rationale: str | None = None


class PublishedModuleMergePoll(BaseModel):
    active: bool
    was_merge: bool
    merged_from_module_id: str | None = None
    proposed_module_id: str | None = None
    proposed_title: str | None = None
    match_rationale: str | None = None
    cards_count: int | None = None
    merged_cards_count: int | None = None
    primary_module_id: str | None = None
    secondary_module_id: str | None = None


class IngestionRunStepPayload(BaseModel):
    id: UUID
    stage: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    input_summary: dict[str, Any] | None
    output_summary: dict[str, Any] | None
    error: dict[str, Any] | None
    error_code: str | None = None
    error_message: str | None = None
    activity: str | None = None
    published_module_merge: PublishedModuleMergePoll | None = None


class IngestionRunDetail(IngestionRunSummary):
    run_kind: str = "pipeline"
    steps: list[IngestionRunStepPayload]
    candidates: list[IngestionRunCandidatePayload] = Field(default_factory=list)
    current_activity: dict[str, Any] | None = None
    source_document_ids: list[str] | None = None
