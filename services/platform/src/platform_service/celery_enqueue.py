"""Enqueue Celery tasks by name without importing worker modules.

API processes, ingest helpers, and workers that chain a follow-up job call
these helpers instead of importing ``celery_tasks``. The worker process still
loads ``celery_tasks`` via ``celery_app.include``.
"""

from celery.result import AsyncResult

from platform_service.celery_app import celery_app
from platform_service.task_names import (
    AGGREGATE_CHAT_FAQS,
    BIND_ASSESSMENT_TRIGGERS,
    CLASSIFY_MODULE_GAPS,
    GENERATE_MODULE_CARD_SEARCH_METADATA_BATCH,
    GENERATE_MODULE_EMBEDDING,
    GENERATE_MODULE_QUIZ,
    GENERATE_MODULE_SEARCH_METADATA,
    GENERATE_SOURCE_THUMBNAIL,
    PROCESS_MODULE_EVENT,
    PROCESS_TRAINING_REQUEST_EVENT,
    PROCESS_VIDEO_PROGRESS_EVENT,
    RETRY_INGEST_CANDIDATE_MERGE,
    RETRY_INGEST_PIPELINE,
    RUN_INGEST_BATCH,
)


def enqueue_process_module_event(payload: dict) -> AsyncResult:
    return celery_app.send_task(PROCESS_MODULE_EVENT, args=[payload])


def enqueue_process_training_request_event(payload: dict) -> AsyncResult:
    return celery_app.send_task(PROCESS_TRAINING_REQUEST_EVENT, args=[payload])


def enqueue_process_video_progress_event(payload: dict) -> AsyncResult:
    return celery_app.send_task(PROCESS_VIDEO_PROGRESS_EVENT, args=[payload])


def enqueue_module_quiz(
    module_id: str,
    step_id: str | None = None,
    *,
    quiz_size: int | None = None,
) -> AsyncResult:
    return celery_app.send_task(
        GENERATE_MODULE_QUIZ,
        args=[module_id, step_id],
        kwargs={"quiz_size": quiz_size},
    )


def enqueue_module_card_search_metadata_batch(
    module_id: str,
    card_step_id: str | None = None,
    metadata_step_id: str | None = None,
    embedding_step_id: str | None = None,
    trigger_binding_step_id: str | None = None,
    *,
    force: bool = False,
    chain_downstream: bool = True,
) -> AsyncResult:
    return celery_app.send_task(
        GENERATE_MODULE_CARD_SEARCH_METADATA_BATCH,
        args=[
            module_id,
            card_step_id,
            metadata_step_id,
            embedding_step_id,
            trigger_binding_step_id,
        ],
        kwargs={"force": force, "chain_downstream": chain_downstream},
    )


def enqueue_module_search_metadata(
    module_id: str,
    step_id: str | None = None,
    embedding_step_id: str | None = None,
    trigger_binding_step_id: str | None = None,
    *,
    chain_downstream: bool = True,
) -> AsyncResult:
    return celery_app.send_task(
        GENERATE_MODULE_SEARCH_METADATA,
        args=[module_id, step_id, embedding_step_id, trigger_binding_step_id],
        kwargs={"chain_downstream": chain_downstream},
    )


def enqueue_bind_assessment_triggers(
    module_id: str,
    step_id: str | None = None,
) -> AsyncResult:
    return celery_app.send_task(BIND_ASSESSMENT_TRIGGERS, args=[module_id, step_id])


def enqueue_module_embedding(module_id: str, step_id: str | None = None) -> AsyncResult:
    return celery_app.send_task(GENERATE_MODULE_EMBEDDING, args=[module_id, step_id])


def enqueue_classify_module_gaps(module_id: str, step_id: str | None = None) -> AsyncResult:
    return celery_app.send_task(CLASSIFY_MODULE_GAPS, args=[module_id, step_id])


def enqueue_source_thumbnail(payload: dict) -> AsyncResult:
    return celery_app.send_task(GENERATE_SOURCE_THUMBNAIL, args=[payload])


def enqueue_run_ingest_batch(payload: dict) -> AsyncResult:
    return celery_app.send_task(RUN_INGEST_BATCH, args=[payload])


def enqueue_retry_ingest_pipeline(payload: dict) -> AsyncResult:
    return celery_app.send_task(RETRY_INGEST_PIPELINE, args=[payload])


def enqueue_retry_ingest_candidate_merge(payload: dict) -> AsyncResult:
    return celery_app.send_task(RETRY_INGEST_CANDIDATE_MERGE, args=[payload])


def enqueue_aggregate_chat_faqs() -> AsyncResult:
    return celery_app.send_task(AGGREGATE_CHAT_FAQS)
