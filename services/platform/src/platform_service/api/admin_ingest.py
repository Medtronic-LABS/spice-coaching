"""Admin v3.3 ingest endpoint — drives a real source document through the
PipelineOrchestrator (Stage A → B → C → D) and exposes status polling.

Distinct from the legacy `POST /admin/documents/upload` (scenarios pipeline
on the Document/Scenario tables); this endpoint operates on the v3.3
`source_document` + `ingestion_run` + `module_candidate_draft` tables.

Endpoints:
  POST /admin/v3/ingest          — upload + start pipeline (background task)
  GET  /admin/v3/ingest/{run_id} — poll run + step state + emitted candidates
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import get_settings
from platform_service.db.base import SessionLocal
from platform_service.db.models.module import Module
from platform_service.db.repositories.module_candidate_repository import (
    ModuleCandidateRepository,
)
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.deps import get_db
from platform_service.services.cross_source_fusion_runner import CrossSourceFusionRunner
from platform_service.services.run_state_service import RunStateService
from platform_service.workers.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/admin/v3", tags=["admin-ingest"])
logger = logging.getLogger(__name__)

_ACCEPTED_SUFFIXES = {".pdf", ".pptx", ".docx"}


def _source_type_from_suffix(suffix: str) -> str:
    return {".pdf": "pdf", ".pptx": "pptx", ".docx": "docx"}[suffix]


# ── Background task ────────────────────────────────────────────────────


async def _run_pipeline_in_background(
    source_document_id: uuid.UUID,
    source_path: str,
    source_type: str,
    primary_language: str,
) -> None:
    """Run the full A→B→C→D pipeline. Uses its own session so the request
    handler's session lifecycle doesn't bind us."""
    try:
        async with SessionLocal() as session:
            orch = PipelineOrchestrator(session)
            result = await orch.run(
                source_document_id=source_document_id,
                source_path=source_path,
                source_type=source_type,
                primary_language=primary_language,
            )
            await session.commit()
            logger.info(
                "Pipeline finished run_id=%s final_status=%s candidates=%d drafts=%d",
                result.run_id,
                result.final_status,
                result.candidates_emitted,
                result.drafts_produced,
            )
    except Exception:
        logger.exception("Pipeline crashed for source_document_id=%s", source_document_id)


# ── Endpoints ──────────────────────────────────────────────────────────


@router.post("/ingest", status_code=202)
async def start_ingest(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Source document (PDF/PPTX/DOCX)"),
    title: str = Form(..., description="Human-readable title for the source"),
    authority_kind: str = Form(
        "official_training",
        description="official_training | sop | refresher | content_update | digital_proficiency",
    ),
    authority_label: str = Form("BRAC", description="Source authority label (e.g. 'BRAC' or 'BBS')"),
    primary_language: str = Form("bn", description="Primary language of the source: 'bn' or 'en'"),
    mode: str = Form(
        "append",
        description=(
            "Workspace handling. 'append' (default): leave existing published modules in "
            "place. 'new': retire all currently-published modules before ingesting (use "
            "this to start a clean workspace, e.g. switching from one program to another)."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Upload a source document and kick off the v3.3 ingestion pipeline."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")
    if mode not in ("append", "new"):
        raise HTTPException(status_code=400, detail=f"invalid mode {mode!r}; must be 'append' or 'new'")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _ACCEPTED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type {suffix!r}; accepted: {sorted(_ACCEPTED_SUFFIXES)}",
        )

    retired_count = 0
    if mode == "new":
        # Fresh workspace: retire every currently-published module BEFORE
        # ingesting the new doc. Retired modules stay in the DB for audit
        # but the Android client filters them out (queries `published`
        # only). No workspace_id, no cascade — `lifecycle_status` is the
        # only state we touch.
        result = await db.execute(
            update(Module)
            .where(Module.lifecycle_status == "published")
            .values(lifecycle_status="retired")
            .returning(Module.id)
        )
        retired_count = len(list(result.scalars().all()))
        logger.info(
            "Ingest mode=new: retired %d published module(s) before fresh ingestion",
            retired_count,
        )

    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = f"{uuid.uuid4()}_{Path(file.filename).name}"
    dest = upload_dir / safe_filename
    content = await file.read()
    dest.write_bytes(content)

    source_repo = SourceRepository(db)
    doc = await source_repo.create_source_document(
        title=title,
        source_type=_source_type_from_suffix(suffix),
        primary_language=primary_language,
        authority_kind=authority_kind,
        authority_label=authority_label,
        original_storage_path=str(dest),
    )
    await db.commit()

    background_tasks.add_task(
        _run_pipeline_in_background,
        doc.id,
        str(dest),
        _source_type_from_suffix(suffix),
        primary_language,
    )
    return {
        "source_document_id": str(doc.id),
        "title": doc.title,
        "source_type": doc.source_type,
        "stored_path": str(dest),
        "status": "pipeline_queued",
        "mode": mode,
        "modules_retired": retired_count,
        "poll_url": f"/admin/v3/ingest/by-document/{doc.id}",
    }


@router.post("/ingest/stream")
async def start_ingest_stream(
    file: UploadFile = File(..., description="Source document (PDF/PPTX/DOCX)"),
    title: str = Form(..., description="Human-readable title for the source"),
    authority_kind: str = Form(
        "official_training",
        description="official_training | sop | refresher | content_update | digital_proficiency",
    ),
    authority_label: str = Form("BRAC", description="Source authority label (e.g. 'BRAC' or 'BBS')"),
    primary_language: str = Form("bn", description="Primary language of the source: 'bn' or 'en'"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Upload a source document and stream SSE pipeline progress events.

    Returns a text/event-stream response. Each event is a JSON line prefixed
    with ``data: `` per the SSE spec. Events:

    - ``run_started``        — pipeline run row created
    - ``stage_started``      — a stage has begun (stage A/B/C/D)
    - ``stage_succeeded``    — a stage completed successfully
    - ``stage_skipped``      — a stage was skipped (resume path)
    - ``stage_failed``       — a stage failed
    - ``pipeline_complete``  — final event with full summary
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _ACCEPTED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type {suffix!r}; accepted: {sorted(_ACCEPTED_SUFFIXES)}",
        )

    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = f"{uuid.uuid4()}_{Path(file.filename).name}"
    dest = upload_dir / safe_filename
    content = await file.read()
    dest.write_bytes(content)

    source_repo = SourceRepository(db)
    doc = await source_repo.create_source_document(
        title=title,
        source_type=_source_type_from_suffix(suffix),
        primary_language=primary_language,
        authority_kind=authority_kind,
        authority_label=authority_label,
        original_storage_path=str(dest),
    )
    await db.commit()

    source_document_id = doc.id
    source_path = str(dest)
    source_type = _source_type_from_suffix(suffix)

    async def event_stream():
        try:
            async with SessionLocal() as stream_session:
                orch = PipelineOrchestrator(stream_session)
                async for event in orch.run_generator(
                    source_document_id=source_document_id,
                    source_path=source_path,
                    source_type=source_type,
                    primary_language=primary_language,
                ):
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception:
            logger.exception("Streaming pipeline crashed for source_document_id=%s", source_document_id)
            yield f"data: {json.dumps({'event': 'error', 'detail': 'pipeline crashed'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/ingest/by-document/{source_document_id}")
async def get_ingest_status_by_document(
    source_document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Look up the most recent ingestion_run for this source_document and
    return its full state + step list + candidate count."""
    state = RunStateService(db)
    # Prefer an active run; fall back to the most recent run regardless of state.
    run = await state.find_active_run(source_document_id)
    if run is None:
        run = await state.find_resumable_run(source_document_id)
    if run is None:
        # No active or resumable run — find the most recent terminal one.
        from sqlalchemy import select

        from platform_service.db.models.ingestion_run import IngestionRun

        result = await db.execute(
            select(IngestionRun)
            .where(IngestionRun.source_document_id == source_document_id)
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        )
        run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="no ingestion_run found for this source_document")
    return await _serialise_run(db, run)


@router.get("/ingest/{run_id}")
async def get_ingest_status(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    state = RunStateService(db)
    run = await state.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"ingestion_run {run_id} not found")
    return await _serialise_run(db, run)


# ── Serialiser ──────────────────────────────────────────────────────────


async def _serialise_run(db: AsyncSession, run) -> dict[str, Any]:
    state = RunStateService(db)
    candidate_repo = ModuleCandidateRepository(db)
    steps = await state.list_steps(run.id)
    candidates = await candidate_repo.list_candidates_for_run(run.id)
    return {
        "run_id": str(run.id),
        "source_document_id": str(run.source_document_id),
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error": run.error_jsonb,
        "steps": [
            {
                "stage": s.stage,
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "input_summary": s.input_summary_jsonb,
                "output_summary": s.output_summary_jsonb,
                "error": s.error_jsonb,
            }
            for s in steps
        ],
        "candidates": [
            {
                "candidate_id": str(c.id),
                "proposed_title": c.proposed_title,
                "behavioural_gap_code": c.behavioural_gap_code,
                "proposed_module_type": c.proposed_module_type,
                "estimated_card_count": c.estimated_card_count,
                "estimated_quiz_count": c.estimated_quiz_count,
                # quality_flags carries the insufficient-source heuristic's
                # advisory flags (architecture-reset). None on candidates
                # produced before that field was wired up.
                "quality_flags": c.quality_flags_jsonb,
            }
            for c in candidates
        ],
    }


# ── Stage 2b: cross-source fusion endpoint ─────────────────────────────


class FusionRequest(BaseModel):
    """Body for POST /admin/v3/fusion. Accepts a list of source_document_id
    UUIDs that have completed Stage 2a (i.e. their per-source ingestion run
    succeeded with at least one candidate). Returns a fusion_run_id the
    caller can use to inspect the resulting fused modules."""

    source_document_ids: list[uuid.UUID] = Field(
        ...,
        min_length=2,
        description=(
            "≥2 source_document_id values to fuse. Each must already have "
            "a completed Stage 2a ingestion run with candidates persisted."
        ),
    )


async def _run_fusion_in_background(source_document_ids: list[uuid.UUID]) -> None:
    """Run the full Stage 2b → Stage 3 → publish flow in a fresh session
    (the request handler's session is gone by the time this runs)."""
    try:
        async with SessionLocal() as session:
            runner = CrossSourceFusionRunner(session)
            summary = await runner.run(source_document_ids)
            logger.info(
                "Fusion run %s finished: input=%d groups=%d published=%d failed=%d coverage_warnings=%d retired=%d",
                summary.fusion_run_id,
                summary.input_candidate_count,
                summary.fusion_group_count,
                summary.fused_modules_published,
                summary.fused_modules_failed,
                summary.fused_modules_with_coverage_warning,
                summary.constituents_retired,
            )
    except Exception:
        logger.exception(
            "Fusion run crashed for source_document_ids=%s",
            [str(d) for d in source_document_ids],
        )


@router.post("/fusion", status_code=202)
async def start_fusion(
    request: FusionRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Trigger a cross-source fusion pass over the specified source documents.

    Each doc's most recent successful Stage 2a candidates are loaded; the
    fuser identifies cross-source pairings; each pair is drafted into a
    fused module whose `source_document_ids` array spans the constituents'
    sources and whose cards cite blocks from each (drafter v2 cross-source
    coverage rule). Constituent per-source modules — i.e. the modules that
    were published from the candidates that ended up in fusion groups —
    are retired (`lifecycle_status='retired'`) so the Android client (which
    filters on `published`) shows only the fused versions. Unfused
    candidates' modules are untouched.

    Returns 202 with a poll URL — actual fusion work runs as a background
    task because Stage 3 drafting is multi-minute.
    """
    background_tasks.add_task(_run_fusion_in_background, list(request.source_document_ids))
    return {
        "status": "fusion_queued",
        "source_document_ids": [str(d) for d in request.source_document_ids],
        "note": (
            "Fusion runs in the background. Inspect resulting modules via the admin "
            "module-list endpoint; published rows with array_length(source_document_ids) "
            ">= 2 are the fused outputs."
        ),
    }
