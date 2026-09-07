"""Celery enqueue helpers for admin ingest."""

from __future__ import annotations

from uuid import UUID

from platform_service.celery_enqueue import (
    enqueue_bind_assessment_triggers,
    enqueue_classify_module_gaps,
    enqueue_module_quiz,
    enqueue_retry_ingest_candidate_merge,
    enqueue_retry_ingest_pipeline,
    enqueue_run_ingest_batch,
    enqueue_source_thumbnail,
)
from platform_service.config import get_settings
from platform_service.services.ingest_upload_service import IngestedSourceResult
from platform_service.services.run_state_service import (
    STAGE_GAP_CLASSIFICATION,
    STAGE_QUIZ_GENERATION,
    STAGE_TRIGGER_BINDING,
)
from platform_service.workers.ingest_worker import IngestJob, ingest_job_to_dict


def ingest_job_from_result(
    result: IngestedSourceResult,
    *,
    run_id: UUID,
    batch_id: UUID,
) -> IngestJob:
    return IngestJob(
        source_document_id=result.source_document_id,
        source_path=result.stored_path,
        source_type=result.source_type,
        primary_language=get_settings().deployment_primary_locale,
        run_id=run_id,
        batch_id=batch_id,
    )


def enqueue_thumbnail_and_batch(
    jobs: list[IngestJob],
    *,
    batch_id: UUID,
) -> None:
    for job in jobs:
        enqueue_source_thumbnail(ingest_job_to_dict(job))

    enqueue_run_ingest_batch(
        {
            "batch_id": str(batch_id),
            "jobs": [ingest_job_to_dict(job) for job in jobs],
        }
    )


def enqueue_thumbnail_retry(
    *,
    source_document_id: UUID,
    source_path: str,
    source_type: str,
    run_id: UUID,
) -> None:
    enqueue_source_thumbnail(
        {
            "source_document_id": str(source_document_id),
            "source_path": source_path,
            "source_type": source_type,
            "primary_language": get_settings().deployment_primary_locale,
            "run_id": str(run_id),
        }
    )


def enqueue_pipeline_resume(
    *,
    source_document_id: UUID,
    source_path: str,
    source_type: str,
    primary_language: str,
    run_id: UUID,
    batch_id: UUID,
    identify_chunk_ids: list[str] | None = None,
    stop_after_identify: bool = False,
    continue_batch: bool = False,
) -> None:
    payload: dict = {
        "source_document_id": str(source_document_id),
        "source_path": source_path,
        "source_type": source_type,
        "primary_language": primary_language,
        "run_id": str(run_id),
        "batch_id": str(batch_id),
    }
    if identify_chunk_ids:
        payload["identify_chunk_ids"] = list(identify_chunk_ids)
    if stop_after_identify:
        payload["stop_after_identify"] = True
    if continue_batch:
        payload["continue_batch"] = True
    enqueue_retry_ingest_pipeline(payload)


def enqueue_candidate_merge_retry(*, batch_id: UUID) -> None:
    enqueue_retry_ingest_candidate_merge({"batch_id": str(batch_id)})


def enqueue_post_publish_step_retry(
    *,
    stage: str,
    module_id: UUID,
    step_id: UUID,
    candidate_id: UUID | None = None,
) -> None:
    """Re-enqueue a single failed post-publish Celery task bound to its step."""
    del candidate_id  # reserved for future quiz_size lookup
    mid = str(module_id)
    sid = str(step_id)
    if stage == STAGE_QUIZ_GENERATION:
        enqueue_module_quiz(mid, sid)
        return
    if stage == STAGE_GAP_CLASSIFICATION:
        enqueue_classify_module_gaps(mid, sid)
        return
    if stage == STAGE_TRIGGER_BINDING:
        enqueue_bind_assessment_triggers(mid, sid)
        return
    raise ValueError(f"unsupported post-publish stage for retry: {stage!r}")
