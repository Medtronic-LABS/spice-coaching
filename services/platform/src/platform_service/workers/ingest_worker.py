"""Ingest background jobs (Celery-backed).

``POST /admin/ingest/upload`` stores bytes; ``POST /admin/ingest`` enqueues
``run_ingest_batch_job``. Each source runs extract + identify, then the batch
merges same-topic candidates, then each successful source drafts. Each job
opens its own DB session(s) — the API request session is not reused.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from mc_contracts.errors import ErrorCode

from platform_service.auth.tenant_context import using_selected_tenant
from platform_service.config import get_settings
from platform_service.db.base import SessionLocal
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.services.attribution_audit import record_attribution_event
from platform_service.services.candidate_merge_runner import CandidateMergeRunner
from platform_service.services.candidate_merger import CandidateMergerError
from platform_service.services.ingest_step_errors import build_step_failure
from platform_service.services.run_state_service import (
    RUN_FAILED,
    RUN_RUNNING,
    ConcurrentRunError,
    RunStateService,
)
from platform_service.services.source_thumbnail_service import source_type_supports_thumbnail
from platform_service.workers.pipeline_orchestrator import PipelineOrchestrator
from platform_service.workers.tenant_binding import ingest_batch_tenant_id, source_document_tenant_id

logger = logging.getLogger(__name__)

_THUMBNAIL_POLL_INTERVAL_S = 0.5


@dataclass(frozen=True)
class IngestJob:
    """Pipeline work for one ingested source_document."""

    source_document_id: UUID
    source_path: str
    source_type: str
    primary_language: str
    run_id: UUID | None = None
    batch_id: UUID | None = None
    identify_chunk_ids: tuple[str, ...] = ()
    stop_after_identify: bool = False
    continue_batch: bool = False


def ingest_job_from_dict(data: dict[str, Any]) -> IngestJob:
    run_raw = data.get("run_id")
    batch_raw = data.get("batch_id")
    raw_chunks = data.get("identify_chunk_ids") or []
    chunk_ids = tuple(str(c) for c in raw_chunks) if isinstance(raw_chunks, list) else ()
    return IngestJob(
        source_document_id=UUID(str(data["source_document_id"])),
        source_path=str(data["source_path"]),
        source_type=str(data["source_type"]),
        primary_language=str(data["primary_language"]),
        run_id=UUID(str(run_raw)) if run_raw else None,
        batch_id=UUID(str(batch_raw)) if batch_raw else None,
        identify_chunk_ids=chunk_ids,
        stop_after_identify=bool(data.get("stop_after_identify")),
        continue_batch=bool(data.get("continue_batch")),
    )


def ingest_job_to_dict(job: IngestJob) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_document_id": str(job.source_document_id),
        "source_path": job.source_path,
        "source_type": job.source_type,
        "primary_language": job.primary_language,
    }
    if job.run_id is not None:
        payload["run_id"] = str(job.run_id)
    if job.batch_id is not None:
        payload["batch_id"] = str(job.batch_id)
    if job.identify_chunk_ids:
        payload["identify_chunk_ids"] = list(job.identify_chunk_ids)
    if job.stop_after_identify:
        payload["stop_after_identify"] = True
    if job.continue_batch:
        payload["continue_batch"] = True
    return payload


async def _mark_active_ingest_failed(source_document_id: UUID) -> None:
    """Mark any running ingestion run as failed after an unexpected crash."""
    async with SessionLocal() as session:
        run_state = RunStateService(session)
        active = await run_state.find_active_run(source_document_id)
        if active is not None:
            user_message, error = build_step_failure(
                error_code=ErrorCode.PIPELINE_CRASHED.value,
                reason="pipeline_crashed",
                technical_message="pipeline crashed",
            )
            error["code"] = ErrorCode.PIPELINE_CRASHED.value
            await run_state.complete_run(
                active.id,
                status=RUN_FAILED,
                error_jsonb=error,
            )
            if active.ingest_batch_id is not None:
                await run_state.refresh_batch_status(active.ingest_batch_id)
            await session.commit()


async def run_pipeline_for_source_job(job: IngestJob) -> None:
    """Run the pipeline for one source_document (full or stop-after-identify)."""
    logger.info("Running pipeline for source_document_id=%s", job.source_document_id)
    tenant_id = await source_document_tenant_id(job.source_document_id)
    with using_selected_tenant(tenant_id):
        try:
            result = await PipelineOrchestrator.run_staged(
                source_document_id=job.source_document_id,
                source_path=job.source_path,
                source_type=job.source_type,
                primary_language=job.primary_language,
                run_id=job.run_id,
                identify_chunk_ids=list(job.identify_chunk_ids) or None,
                stop_after_identify=job.stop_after_identify,
            )
            async with SessionLocal() as session:
                if not job.stop_after_identify:
                    await record_attribution_event(
                        session,
                        event_type="ingest_completed",
                        actor="system",
                        source_document_id=job.source_document_id,
                        payload={"final_status": result.final_status, "run_id": str(result.run_id)},
                    )
                if job.batch_id is not None:
                    await RunStateService(session).refresh_batch_status(job.batch_id)
                await session.commit()
            logger.info(
                "Pipeline finished run_id=%s final_status=%s candidates=%d drafts=%d stop_after_identify=%s",
                result.run_id,
                result.final_status,
                result.candidates_emitted,
                result.drafts_produced,
                job.stop_after_identify,
            )
            if job.continue_batch and job.batch_id is not None:
                await _merge_and_draft_batch(job.batch_id)
        except ConcurrentRunError:
            logger.warning(
                "Skipping ingest for source_document_id=%s — another worker owns the active run",
                job.source_document_id,
            )
            return
        except Exception:
            logger.exception("Pipeline crashed for source_document_id=%s", job.source_document_id)
            try:
                await _mark_active_ingest_failed(job.source_document_id)
            except Exception:
                logger.exception("Failed to mark ingestion run failed for %s", job.source_document_id)
            try:
                async with SessionLocal() as failure_session:
                    await record_attribution_event(
                        failure_session,
                        event_type="ingest_failed",
                        actor="system",
                        source_document_id=job.source_document_id,
                        payload={"detail": "pipeline crashed"},
                    )
                    await failure_session.commit()
            except Exception:
                logger.exception("Failed to record ingest_failed for %s", job.source_document_id)
            raise


async def _wait_for_thumbnail_ready(job: IngestJob) -> None:
    """Poll for thumbnail_storage_path set by the upload-time Celery task."""
    if not source_type_supports_thumbnail(job.source_type):
        return

    settings = get_settings()
    deadline = time.monotonic() + settings.ingest_thumbnail_wait_seconds
    logger.info(
        "Waiting for thumbnail source_document_id=%s timeout_seconds=%d",
        job.source_document_id,
        settings.ingest_thumbnail_wait_seconds,
    )
    try:
        while time.monotonic() < deadline:
            async with SessionLocal() as session:
                doc = await SourceRepository(session).get_source_document(job.source_document_id)
                if doc is not None and doc.thumbnail_storage_path:
                    logger.info(
                        "Thumbnail ready source_document_id=%s path=%s",
                        job.source_document_id,
                        doc.thumbnail_storage_path,
                    )
                    return
            await asyncio.sleep(_THUMBNAIL_POLL_INTERVAL_S)
        logger.warning(
            "Thumbnail wait timed out source_document_id=%s after %ds",
            job.source_document_id,
            settings.ingest_thumbnail_wait_seconds,
        )
        raise TimeoutError(f"thumbnail did not complete within {settings.ingest_thumbnail_wait_seconds}s")
    except Exception:
        logger.warning(
            "Thumbnail task did not complete for source_document_id=%s; continuing ingest",
            job.source_document_id,
            exc_info=True,
        )


async def _draft_jobs_for_batch(batch_id: UUID) -> list[IngestJob]:
    """Build draft-resume jobs for identify-succeeded running sources."""
    async with SessionLocal() as session:
        run_state = RunStateService(session)
        sources = SourceRepository(session)
        runs = await run_state.list_runs_for_batch(batch_id)
        jobs: list[IngestJob] = []
        for run in runs:
            if run.status != RUN_RUNNING:
                continue
            if not await run_state.is_module_identify_fully_succeeded(run.id):
                continue
            doc = await sources.get_source_document(run.source_document_id)
            if doc is None:
                continue
            jobs.append(
                IngestJob(
                    source_document_id=run.source_document_id,
                    source_path=doc.original_storage_path,
                    source_type=doc.source_type,
                    primary_language=doc.primary_language,
                    run_id=run.id,
                    batch_id=batch_id,
                    stop_after_identify=False,
                )
            )
        return jobs


async def _merge_and_draft_batch(batch_id: UUID) -> None:
    """Run candidate merge then Stage D for identify-succeeded sources.

    Binds the batch tenant so Stage C/D create/merge paths that call
    ``require_selected_tenant_id`` succeed outside per-source pipeline scopes.
    """
    tenant_id = await ingest_batch_tenant_id(batch_id)
    with using_selected_tenant(tenant_id):
        try:
            summary = await CandidateMergeRunner.run_staged(batch_id)
        except CandidateMergerError:
            logger.exception("Candidate merge failed for batch_id=%s", batch_id)
            async with SessionLocal() as session:
                await RunStateService(session).refresh_batch_status(batch_id)
                await session.commit()
            return
        logger.info(
            "Candidate merge batch_id=%s input=%d groups=%d skipped=%s succeeded=%s",
            batch_id,
            summary.input_candidate_count,
            summary.group_count,
            summary.skipped,
            summary.succeeded,
        )
        if not summary.succeeded:
            async with SessionLocal() as session:
                await RunStateService(session).refresh_batch_status(batch_id)
                await session.commit()
            return
        for job in await _draft_jobs_for_batch(batch_id):
            await run_pipeline_for_source_job(job)


async def run_candidate_merge_job(payload: dict[str, Any]) -> None:
    """Retry entry: merge then draft for one ingest batch."""
    batch_id = UUID(str(payload["batch_id"]))
    await _merge_and_draft_batch(batch_id)


async def run_ingest_batch_job(payload: dict[str, Any]) -> None:
    """Identify all sources, merge same-topic candidates, then draft."""
    jobs = [ingest_job_from_dict(j) for j in payload["jobs"]]
    batch_raw = payload.get("batch_id")
    batch_id = UUID(str(batch_raw)) if batch_raw else None
    for job in jobs:
        await _wait_for_thumbnail_ready(job)
        identify_job = IngestJob(
            source_document_id=job.source_document_id,
            source_path=job.source_path,
            source_type=job.source_type,
            primary_language=job.primary_language,
            run_id=job.run_id,
            batch_id=job.batch_id or batch_id,
            identify_chunk_ids=job.identify_chunk_ids,
            stop_after_identify=True,
        )
        await run_pipeline_for_source_job(identify_job)
    if batch_id is not None:
        await _merge_and_draft_batch(batch_id)
        async with SessionLocal() as session:
            await RunStateService(session).refresh_batch_status(batch_id)
            await session.commit()
