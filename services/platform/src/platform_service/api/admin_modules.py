"""Admin dashboard endpoints — modules, trigger bindings, ingestion runs.

Per `docs/ARCHITECTURE_RESET.md`. Replaces the deleted W-6 reviewer-queue
surface (`api/admin_reviewer.py`). The dashboard is a quality-assurance UI
on already-published content, not a publish gate. All endpoints write
through `ModuleRepository`; quiz questions are joined from
`module_quiz_question` for the per-module read.

Endpoint summary:
  GET    /admin/modules                          list with filters
  GET    /admin/modules/{id}                     full payload (cards + quiz)
  PUT    /admin/modules/{id}                     create new version with edits
  POST   /admin/modules/{id}/clinically-reviewed flip the QA flag
  POST   /admin/modules/{id}/visibility-window   set/clear the "what's new" range
  DELETE /admin/modules/{id}                     retire (soft-delete)
  POST   /admin/modules/search                   semantic-similarity search
  POST   /admin/modules/{id}/regenerate-quiz      enqueue quiz Celery task
  POST   /admin/modules/{id}/regenerate-embedding enqueue embedding Celery task

  GET    /admin/trigger-bindings/by-module/{family_id}
  POST   /admin/trigger-bindings
  PUT    /admin/trigger-bindings/{id}
  DELETE /admin/trigger-bindings/{id}

  GET    /admin/ingestion-runs                   list recent runs
  GET    /admin/ingestion-runs/{id}              run detail + step rows
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.ingestion_run import IngestionRun, IngestionRunStep
from platform_service.db.models.module import Module
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
from platform_service.db.models.trigger_definition import (
    ModuleTriggerBinding,
    TriggerDefinition,
)
from platform_service.db.repositories.module_repository import (
    ModuleNotFoundError,
    ModuleRepository,
)
from platform_service.db.repositories.trigger_repository import TriggerRepository
from platform_service.deps import get_db

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])
logger = logging.getLogger(__name__)


# ─── Module payload shape ─────────────────────────────────────────────────


class ModuleSummary(BaseModel):
    """List-row response. Keeps the payload light; full content via GET /modules/:id."""

    id: UUID
    module_family_id: UUID
    version: int
    title_bn: str
    title_en: str | None
    description_bn: str | None
    domain: str
    module_type: str
    lifecycle_status: str
    clinically_reviewed: bool
    has_visibility_window: bool
    card_count: int
    quiz_count: int
    estimated_minutes: int
    published_at: datetime | None
    created_at: datetime
    # Quality flags written by Stage 2 / Stage 2-draft (e.g.
    # `insufficient_source_filter`, drafter `insufficient_reason`). Surfaced
    # so the dashboard can build a "needs attention" view; presence of any
    # flag does NOT block publish.
    quality_flags: dict[str, Any] | None


class QuizQuestionPayload(BaseModel):
    id: UUID
    question_order: int | None
    question_bn: str
    question_en: str | None
    case_setup_bn: str | None
    case_setup_en: str | None
    options_bn: list[Any]
    options_en: list[Any] | None
    correct_indices: list[int]
    explanation_bn: str | None
    explanation_en: str | None
    difficulty: str


class ModuleDetail(ModuleSummary):
    """Full module: shell + cards + quiz."""

    cards: list[dict[str, Any]]
    quiz: list[QuizQuestionPayload]
    sub_domain: str | None
    estimated_minutes: int
    difficulty_level: str
    pass_threshold_override: float | None
    visibility_window_lower: datetime | None
    visibility_window_upper: datetime | None


def _summary_from_module(module, *, card_count: int, quiz_count: int) -> ModuleSummary:
    return ModuleSummary(
        id=module.id,
        module_family_id=module.module_family_id,
        version=module.version,
        title_bn=module.title_bn,
        title_en=module.title_en,
        description_bn=module.description_bn,
        domain=module.domain,
        module_type=module.module_type,
        lifecycle_status=module.lifecycle_status,
        clinically_reviewed=module.clinically_reviewed,
        has_visibility_window=module.visibility_window is not None,
        card_count=card_count,
        quiz_count=quiz_count,
        estimated_minutes=module.estimated_minutes,
        published_at=module.published_at,
        created_at=module.created_at,
        quality_flags=module.quality_flags_jsonb,
    )


def _quiz_payload(rows) -> list[QuizQuestionPayload]:
    return [
        QuizQuestionPayload(
            id=r.id,
            question_order=r.question_order,
            question_bn=r.question_bn,
            question_en=r.question_en,
            case_setup_bn=r.case_setup_bn,
            case_setup_en=r.case_setup_en,
            options_bn=list(r.options_bn or []),
            options_en=list(r.options_en) if r.options_en else None,
            correct_indices=list(r.correct_indices or []),
            explanation_bn=r.explanation_bn,
            explanation_en=r.explanation_en,
            difficulty=r.difficulty,
        )
        for r in rows
    ]


async def _get_quiz_counts(session: AsyncSession, module_ids: list[UUID]) -> dict[UUID, int]:
    if not module_ids:
        return {}
    stmt = (
        select(ModuleQuizQuestion.module_id, func.count(ModuleQuizQuestion.id))
        .where(ModuleQuizQuestion.module_id.in_(module_ids))
        .group_by(ModuleQuizQuestion.module_id)
    )
    result = await session.execute(stmt)
    return {r[0]: r[1] for r in result.all()}


# ─── Module endpoints ─────────────────────────────────────────────────────


@router.get("/modules", response_model=list[ModuleSummary])
async def list_modules(
    status: str | None = Query(None, description="draft | published | retired"),
    clinically_reviewed: bool | None = Query(None),
    has_visibility_window: bool | None = Query(None),
    has_quality_flags: bool | None = Query(
        None,
        description="true → only modules with non-empty quality_flags_jsonb (the 'needs attention' view)",
    ),
    domain: str | None = Query(None),
    q: str | None = Query(None, description="full-text query against title + description"),
    latest_version_only: bool = Query(
        True,
        description="When true (default), collapse to one row per module_family showing the highest-version row that matches filters. Set false to see every version.",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[ModuleSummary]:
    repo = ModuleRepository(session)
    modules = await repo.list_modules(
        status=status,
        clinically_reviewed=clinically_reviewed,
        has_visibility_window=has_visibility_window,
        has_quality_flags=has_quality_flags,
        domain=domain,
        full_text_query=q,
        latest_version_only=latest_version_only,
        limit=limit,
        offset=offset,
    )
    quiz_counts = await _get_quiz_counts(session, [m.id for m in modules])
    return [
        _summary_from_module(
            m, 
            card_count=len((m.module_json or {}).get("cards", [])),
            quiz_count=quiz_counts.get(m.id, 0)
        ) 
        for m in modules
    ]


@router.get("/modules/{module_id}", response_model=ModuleDetail)
async def get_module(
    module_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> ModuleDetail:
    repo = ModuleRepository(session)
    module = await repo.get_module(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="module not found")
    quiz = await repo.list_quiz_questions(module_id)
    cards = list((module.module_json or {}).get("cards", []))
    summary = _summary_from_module(module, card_count=len(cards), quiz_count=len(quiz))
    window_lower: datetime | None = None
    window_upper: datetime | None = None
    if module.visibility_window is not None:
        # PostgreSQL TSTZRANGE comes back as a Range object with .lower / .upper.
        window_lower = getattr(module.visibility_window, "lower", None)
        window_upper = getattr(module.visibility_window, "upper", None)
    return ModuleDetail(
        **summary.model_dump(),
        cards=cards,
        quiz=_quiz_payload(quiz),
        sub_domain=module.sub_domain,
        difficulty_level=module.difficulty_level,
        pass_threshold_override=module.pass_threshold_override,
        visibility_window_lower=window_lower,
        visibility_window_upper=window_upper,
    )


class QuizQuestionEditRequest(BaseModel):
    id: str | None = None
    question_order: int | None = None
    question_bn: str | None = None
    question_en: str | None = None
    case_setup_bn: str | None = None
    case_setup_en: str | None = None
    options_bn: list[Any]
    options_en: list[Any] | None = None
    correct_indices: list[int]
    explanation_bn: str | None = None
    explanation_en: str | None = None
    difficulty: str = "moderate"


class ModuleEditRequest(BaseModel):
    title_bn: str | None = None
    title_en: str | None = None
    description_bn: str | None = None
    module_json: dict[str, Any] | None = None
    editor_id: UUID | None = None
    quiz: list[QuizQuestionEditRequest] | None = None


@router.put("/modules/{module_id}")
async def edit_module(
    module_id: UUID,
    body: ModuleEditRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repo = ModuleRepository(session)
    try:
        new_module = await repo.edit_module(
            module_id,
            title_bn=body.title_bn,
            title_en=body.title_en,
            description_bn=body.description_bn,
            module_json=body.module_json,
            editor_id=body.editor_id,
        )
        
        quiz_data = body.quiz
        if quiz_data is None and body.module_json is not None:
            quiz_data = body.module_json.get("quiz")
            
        if quiz_data is not None:
            for idx, q_item in enumerate(quiz_data, start=1):
                if isinstance(q_item, dict):
                    q = QuizQuestionEditRequest(**q_item)
                else:
                    q = q_item
                    
                question_family_id = uuid.uuid4()
                question_version = 1
                
                if q.id is not None and q.id != "":
                    try:
                        u_id = UUID(str(q.id))
                        stmt = select(ModuleQuizQuestion).where(ModuleQuizQuestion.id == u_id)
                        existing_q = (await session.execute(stmt)).scalar_one_or_none()
                        if existing_q:
                            question_family_id = existing_q.question_family_id
                            stmt_max = select(func.max(ModuleQuizQuestion.question_version)).where(
                                ModuleQuizQuestion.question_family_id == question_family_id
                            )
                            max_v = (await session.execute(stmt_max)).scalar_one() or 0
                            question_version = max_v + 1
                    except ValueError:
                        # Not a valid UUID, ignore it and treat as new question
                        pass
                
                row = ModuleQuizQuestion(
                    module_id=new_module.id,
                    question_order=q.question_order if q.question_order is not None else idx,
                    question_family_id=question_family_id,
                    question_version=question_version,
                    case_setup_en=q.case_setup_en,
                    case_setup_bn=q.case_setup_bn,
                    question_en=q.question_en,
                    question_bn=q.question_bn or "",  # Fallback to empty string if null
                    question_type="single_select",
                    options_en=q.options_en,
                    options_bn=q.options_bn,
                    correct_indices=q.correct_indices,
                    explanation_en=q.explanation_en,
                    explanation_bn=q.explanation_bn,
                    difficulty=q.difficulty,
                )
                session.add(row)
                
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return {
        "id": str(new_module.id),
        "module_family_id": str(new_module.module_family_id),
        "version": new_module.version,
        "supersedes_module_id": str(new_module.supersedes_module_id)
        if new_module.supersedes_module_id
        else None,
    }


class ClinicalFlagRequest(BaseModel):
    clinically_reviewed: bool
    reviewer_id: UUID | None = None


@router.post("/modules/{module_id}/clinically-reviewed")
async def set_clinically_reviewed(
    module_id: UUID,
    body: ClinicalFlagRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repo = ModuleRepository(session)
    try:
        module = await repo.set_clinically_reviewed(
            module_id, flag=body.clinically_reviewed, reviewer_id=body.reviewer_id
        )
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return {
        "id": str(module.id),
        "clinically_reviewed": module.clinically_reviewed,
        "clinically_reviewed_at": module.clinically_reviewed_at,
        "clinically_reviewed_by": str(module.clinically_reviewed_by)
        if module.clinically_reviewed_by
        else None,
    }


class VisibilityWindowRequest(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None


@router.post("/modules/{module_id}/visibility-window")
async def set_visibility_window(
    module_id: UUID,
    body: VisibilityWindowRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Set a visibility window for the "what's new" runtime flow. Pass
    `starts_at=null, ends_at=null` to clear the window."""
    # asyncpg's native Range type roundtrips cleanly into the TSTZRANGE
    # column. Half-open `[lower, upper)` matches Postgres convention so
    # `now() <@ visibility_window` excludes the upper bound at expiry.
    from asyncpg import Range  # type: ignore[import-untyped]

    repo = ModuleRepository(session)
    window: Range | None
    if body.starts_at is None and body.ends_at is None:
        window = None
    else:
        window = Range(body.starts_at, body.ends_at, lower_inc=True, upper_inc=False)
    try:
        module = await repo.set_visibility_window(module_id, window=window)
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return {
        "id": str(module.id),
        "visibility_window": (
            None
            if module.visibility_window is None
            else {
                "lower": getattr(module.visibility_window, "lower", None),
                "upper": getattr(module.visibility_window, "upper", None),
            }
        ),
    }


@router.delete("/modules/{module_id}")
async def retire_module(
    module_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repo = ModuleRepository(session)
    try:
        module = await repo.retire_module(module_id)
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return {
        "id": str(module.id),
        "lifecycle_status": module.lifecycle_status,
        "deprecated_at": module.deprecated_at,
    }


class SemanticSearchRequest(BaseModel):
    """Either a free-text query (server embeds it via ai-runtime) or a
    precomputed embedding vector. Callers without an embedding pipeline of
    their own should send `query` — the dashboard FE has no need to call
    /embed itself.
    """

    query: str | None = Field(
        None, description="free-text query; server embeds via ai-runtime before searching"
    )
    query_vector: list[float] | None = Field(
        None, description="precomputed embedding vector (escape hatch for batch tooling)"
    )
    limit: int = Field(10, ge=1, le=50)


@router.post("/modules/search", response_model=list[ModuleSummary])
async def semantic_search(
    body: SemanticSearchRequest,
    session: AsyncSession = Depends(get_db),
) -> list[ModuleSummary]:
    if body.query is None and body.query_vector is None:
        raise HTTPException(status_code=400, detail="provide either `query` or `query_vector`")
    if body.query_vector is not None:
        vec = body.query_vector
    else:
        # Embed the user-supplied string via ai-runtime. Lazy import keeps
        # the admin module testable without spinning up an ai-runtime.
        from platform_service.integrations.ai_runtime_client import AIRuntimeClient

        client = AIRuntimeClient()
        vectors = await client.embed([body.query or ""])
        if not vectors:
            raise HTTPException(status_code=502, detail="ai-runtime returned no embedding")
        vec = vectors[0]
    repo = ModuleRepository(session)
    pairs = await repo.search_by_embedding(query_vector=vec, limit=body.limit)
    modules = [m for m, _distance in pairs]
    quiz_counts = await _get_quiz_counts(session, [m.id for m in modules])
    return [
        _summary_from_module(
            m, 
            card_count=len((m.module_json or {}).get("cards", [])),
            quiz_count=quiz_counts.get(m.id, 0)
        )
        for m in modules
    ]


# ─── Post-publish regenerate endpoints ────────────────────────────────────


@router.post("/modules/{module_id}/regenerate-quiz")
async def regenerate_quiz(
    module_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Re-enqueue the quiz Celery task for a published module. Use when the
    auto-publish post-publish job exhausted retries (or returned malformed
    JSON the first time)."""
    if await session.get(Module, module_id) is None:
        raise HTTPException(status_code=404, detail="module not found")
    from platform_service.celery_tasks import generate_module_quiz_task

    generate_module_quiz_task.delay(str(module_id))
    return {"id": str(module_id), "enqueued": "platform.generate_module_quiz"}


@router.post("/modules/{module_id}/regenerate-embedding")
async def regenerate_embedding(
    module_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Re-enqueue the embedding Celery task for a published module. Use
    when ai-runtime was down on the original publish or the embedding
    needs recomputing after content edits."""
    if await session.get(Module, module_id) is None:
        raise HTTPException(status_code=404, detail="module not found")
    from platform_service.celery_tasks import generate_module_embedding_task

    generate_module_embedding_task.delay(str(module_id))
    return {"id": str(module_id), "enqueued": "platform.generate_module_embedding"}


# ─── Trigger binding endpoints ────────────────────────────────────────────


class TriggerBindingPayload(BaseModel):
    id: UUID
    trigger_definition_id: UUID
    module_family_id: UUID
    # primary | secondary — bindings have no on/off flag; deactivation is
    # done via DELETE.
    relationship: str
    # Higher = preferred when multiple modules match the same trigger.
    priority_weight: int
    notes: str | None


def _binding_to_payload(b: ModuleTriggerBinding) -> TriggerBindingPayload:
    return TriggerBindingPayload(
        id=b.id,
        trigger_definition_id=b.trigger_definition_id,
        module_family_id=b.module_family_id,
        relationship=b.relationship,
        priority_weight=b.priority_weight,
        notes=b.notes,
    )


@router.get("/trigger-bindings/by-module/{module_family_id}", response_model=list[TriggerBindingPayload])
async def list_bindings_for_family(
    module_family_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[TriggerBindingPayload]:
    repo = TriggerRepository(session)
    bindings = await repo.list_bindings_for_module_family(module_family_id)
    return [_binding_to_payload(b) for b in bindings]


class CreateBindingRequest(BaseModel):
    trigger_definition_id: UUID
    module_family_id: UUID
    relationship: str = "primary"
    priority_weight: int = 10
    notes: str | None = None


@router.post("/trigger-bindings", response_model=TriggerBindingPayload)
async def create_binding(
    body: CreateBindingRequest,
    session: AsyncSession = Depends(get_db),
) -> TriggerBindingPayload:
    repo = TriggerRepository(session)
    binding = await repo.bind_module_to_trigger(
        trigger_definition_id=body.trigger_definition_id,
        module_family_id=body.module_family_id,
        relationship=body.relationship,
        priority_weight=body.priority_weight,
        notes=body.notes,
    )
    await session.commit()
    return _binding_to_payload(binding)


class UpdateBindingRequest(BaseModel):
    relationship: str | None = None
    priority_weight: int | None = None
    notes: str | None = None


@router.put("/trigger-bindings/{binding_id}", response_model=TriggerBindingPayload)
async def update_binding(
    binding_id: UUID,
    body: UpdateBindingRequest,
    session: AsyncSession = Depends(get_db),
) -> TriggerBindingPayload:
    binding = await session.get(ModuleTriggerBinding, binding_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="trigger binding not found")
    if body.relationship is not None:
        if body.relationship not in ("primary", "secondary"):
            raise HTTPException(
                status_code=400,
                detail="relationship must be 'primary' or 'secondary'",
            )
        binding.relationship = body.relationship
    if body.priority_weight is not None:
        binding.priority_weight = body.priority_weight
    if body.notes is not None:
        binding.notes = body.notes
    await session.flush()
    await session.commit()
    return _binding_to_payload(binding)


@router.delete("/trigger-bindings/{binding_id}")
async def delete_binding(
    binding_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    binding = await session.get(ModuleTriggerBinding, binding_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="trigger binding not found")
    await session.delete(binding)
    await session.commit()
    return {"id": str(binding_id), "deleted": True}


# ─── Ingestion run endpoints ──────────────────────────────────────────────


class IngestionRunSummary(BaseModel):
    id: UUID
    source_document_id: UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    error: dict[str, Any] | None


class IngestionRunStepPayload(BaseModel):
    id: UUID
    stage: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    input_summary: dict[str, Any] | None
    output_summary: dict[str, Any] | None
    error: dict[str, Any] | None


class IngestionRunDetail(IngestionRunSummary):
    steps: list[IngestionRunStepPayload]


@router.get("/ingestion-runs", response_model=list[IngestionRunSummary])
async def list_ingestion_runs(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[IngestionRunSummary]:
    stmt = select(IngestionRun)
    if status:
        stmt = stmt.where(IngestionRun.status == status)
    stmt = stmt.order_by(IngestionRun.started_at.desc()).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        IngestionRunSummary(
            id=r.id,
            source_document_id=r.source_document_id,
            status=r.status,
            started_at=r.started_at,
            completed_at=r.completed_at,
            error=r.error_jsonb,
        )
        for r in rows
    ]


@router.get("/ingestion-runs/{run_id}", response_model=IngestionRunDetail)
async def get_ingestion_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> IngestionRunDetail:
    run = await session.get(IngestionRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="ingestion run not found")
    step_rows = list(
        (
            await session.execute(
                select(IngestionRunStep)
                .where(IngestionRunStep.ingestion_run_id == run_id)
                .order_by(IngestionRunStep.started_at.asc().nullslast())
            )
        )
        .scalars()
        .all()
    )
    return IngestionRunDetail(
        id=run.id,
        source_document_id=run.source_document_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error=run.error_jsonb,
        steps=[
            IngestionRunStepPayload(
                id=s.id,
                stage=s.stage,
                status=s.status,
                started_at=s.started_at,
                completed_at=s.completed_at,
                input_summary=s.input_summary_jsonb,
                output_summary=s.output_summary_jsonb,
                error=s.error_jsonb,
            )
            for s in step_rows
        ],
    )


# Suppress unused-import lint when only the type is referenced via Pydantic.
_ = TriggerDefinition
