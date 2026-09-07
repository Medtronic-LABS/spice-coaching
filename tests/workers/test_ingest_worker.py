"""Tests for ingest batch worker thumbnail ordering."""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from platform_service.auth.tenant_context import require_selected_tenant_id
from platform_service.services.candidate_merge_runner import CandidateMergeSummary
from platform_service.workers.ingest_worker import (
    IngestJob,
    _merge_and_draft_batch,
    run_ingest_batch_job,
)

_BUCKET = "medtronics-storage"


def _job_payload(*jobs: IngestJob) -> dict:
    return {
        "jobs": [
            {
                "source_document_id": str(job.source_document_id),
                "source_path": job.source_path,
                "source_type": job.source_type,
                "primary_language": job.primary_language,
            }
            for job in jobs
        ],
    }


@contextmanager
def _mock_thumbnail_polling(*, get_source_document: AsyncMock):
    mock_repo = MagicMock()
    mock_repo.get_source_document = get_source_document

    @asynccontextmanager
    async def _session_local():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    with (
        patch(
            "platform_service.workers.ingest_worker.SourceRepository",
            return_value=mock_repo,
        ),
        patch("platform_service.workers.ingest_worker.SessionLocal", _session_local),
    ):
        yield


@pytest.mark.asyncio
async def test_batch_continues_when_thumbnail_task_fails() -> None:
    job = IngestJob(
        source_document_id=uuid4(),
        source_path=f"{_BUCKET}/ingest/x.pdf",
        source_type="pdf",
        primary_language="bn",
    )
    doc_without_thumb = MagicMock()
    doc_without_thumb.thumbnail_storage_path = None
    get_source_document = AsyncMock(return_value=doc_without_thumb)

    settings = MagicMock()
    settings.ingest_thumbnail_wait_seconds = 0

    with (
        patch("platform_service.celery_enqueue.enqueue_source_thumbnail") as mock_thumb_task,
        _mock_thumbnail_polling(get_source_document=get_source_document),
        patch("platform_service.workers.ingest_worker.get_settings", return_value=settings),
        patch(
            "platform_service.workers.ingest_worker.run_pipeline_for_source_job",
            new_callable=AsyncMock,
        ) as mock_pipeline,
    ):
        await run_ingest_batch_job(_job_payload(job))

    mock_thumb_task.assert_not_called()
    mock_pipeline.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_waits_for_thumbnail_before_pipeline() -> None:
    job = IngestJob(
        source_document_id=uuid4(),
        source_path=f"{_BUCKET}/ingest/x.pdf",
        source_type="pdf",
        primary_language="bn",
    )
    call_order: list[str] = []
    doc_without_thumb = MagicMock()
    doc_without_thumb.thumbnail_storage_path = None
    doc_with_thumb = MagicMock()
    doc_with_thumb.thumbnail_storage_path = f"{_BUCKET}/ingest/thumbnails/{job.source_document_id}.png"

    poll_count = 0

    async def get_source_document(_doc_id):
        nonlocal poll_count
        poll_count += 1
        call_order.append("thumbnail_poll")
        if poll_count < 2:
            return doc_without_thumb
        return doc_with_thumb

    settings = MagicMock()
    settings.ingest_thumbnail_wait_seconds = 30

    async def record_pipeline(_job: IngestJob) -> None:
        call_order.append("pipeline")

    with (
        patch("platform_service.celery_enqueue.enqueue_source_thumbnail") as mock_thumb_task,
        _mock_thumbnail_polling(get_source_document=AsyncMock(side_effect=get_source_document)),
        patch("platform_service.workers.ingest_worker.get_settings", return_value=settings),
        patch(
            "platform_service.workers.ingest_worker.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        patch(
            "platform_service.workers.ingest_worker.run_pipeline_for_source_job",
            side_effect=record_pipeline,
        ),
    ):
        await run_ingest_batch_job(_job_payload(job))

    mock_thumb_task.assert_not_called()
    assert call_order.index("pipeline") > call_order.index("thumbnail_poll")
    assert poll_count >= 2


@pytest.mark.asyncio
async def test_batch_logs_thumbnail_wait_lifecycle(caplog: pytest.LogCaptureFixture) -> None:
    job = IngestJob(
        source_document_id=uuid4(),
        source_path=f"{_BUCKET}/ingest/x.pdf",
        source_type="pdf",
        primary_language="bn",
    )
    doc_with_thumb = MagicMock()
    doc_with_thumb.thumbnail_storage_path = f"{_BUCKET}/ingest/thumbnails/{job.source_document_id}.png"

    settings = MagicMock()
    settings.ingest_thumbnail_wait_seconds = 30

    with (
        patch("platform_service.celery_enqueue.enqueue_source_thumbnail"),
        _mock_thumbnail_polling(get_source_document=AsyncMock(return_value=doc_with_thumb)),
        patch("platform_service.workers.ingest_worker.get_settings", return_value=settings),
        patch(
            "platform_service.workers.ingest_worker.run_pipeline_for_source_job",
            new_callable=AsyncMock,
        ),
        caplog.at_level("INFO", logger="platform_service.workers.ingest_worker"),
    ):
        await run_ingest_batch_job(_job_payload(job))

    messages = [record.message for record in caplog.records]
    assert any("Waiting for thumbnail" in message for message in messages)
    assert any("Thumbnail ready" in message for message in messages)


@pytest.mark.asyncio
async def test_batch_skips_thumbnail_wait_for_unsupported_source_type() -> None:
    job = IngestJob(
        source_document_id=uuid4(),
        source_path=f"{_BUCKET}/ingest/x.docx",
        source_type="docx",
        primary_language="bn",
    )
    get_source_document = AsyncMock()

    with (
        patch("platform_service.celery_enqueue.enqueue_source_thumbnail") as mock_thumb_task,
        _mock_thumbnail_polling(get_source_document=get_source_document),
        patch(
            "platform_service.workers.ingest_worker.run_pipeline_for_source_job",
            new_callable=AsyncMock,
        ) as mock_pipeline,
    ):
        await run_ingest_batch_job(_job_payload(job))

    get_source_document.assert_not_called()
    mock_thumb_task.assert_not_called()
    mock_pipeline.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_identifies_then_merges_for_two_jobs() -> None:
    batch_id = uuid4()
    jobs = [
        IngestJob(
            source_document_id=uuid4(),
            source_path=f"{_BUCKET}/ingest/a.pdf",
            source_type="pdf",
            primary_language="bn",
        ),
        IngestJob(
            source_document_id=uuid4(),
            source_path=f"{_BUCKET}/ingest/b.pdf",
            source_type="pdf",
            primary_language="bn",
        ),
    ]
    settings = MagicMock()
    settings.ingest_thumbnail_wait_seconds = 0
    doc = MagicMock()
    doc.thumbnail_storage_path = None
    payload = _job_payload(*jobs)
    payload["batch_id"] = str(batch_id)

    with (
        patch("platform_service.celery_enqueue.enqueue_source_thumbnail"),
        _mock_thumbnail_polling(get_source_document=AsyncMock(return_value=doc)),
        patch("platform_service.workers.ingest_worker.get_settings", return_value=settings),
        patch(
            "platform_service.workers.ingest_worker.run_pipeline_for_source_job",
            new_callable=AsyncMock,
        ) as mock_pipeline,
        patch(
            "platform_service.workers.ingest_worker._merge_and_draft_batch",
            new_callable=AsyncMock,
        ) as mock_merge,
        patch(
            "platform_service.workers.ingest_worker.RunStateService",
            return_value=MagicMock(refresh_batch_status=AsyncMock()),
        ),
    ):
        await run_ingest_batch_job(payload)

    assert mock_pipeline.await_count == 2
    for call in mock_pipeline.await_args_list:
        identify_job: IngestJob = call.args[0]
        assert identify_job.stop_after_identify is True
    mock_merge.assert_awaited_once_with(batch_id)


@pytest.mark.asyncio
async def test_batch_merges_for_single_job() -> None:
    batch_id = uuid4()
    job = IngestJob(
        source_document_id=uuid4(),
        source_path=f"{_BUCKET}/ingest/x.pdf",
        source_type="pdf",
        primary_language="bn",
    )
    settings = MagicMock()
    settings.ingest_thumbnail_wait_seconds = 0
    doc = MagicMock()
    doc.thumbnail_storage_path = None
    payload = _job_payload(job)
    payload["batch_id"] = str(batch_id)

    with (
        patch("platform_service.celery_enqueue.enqueue_source_thumbnail"),
        _mock_thumbnail_polling(get_source_document=AsyncMock(return_value=doc)),
        patch("platform_service.workers.ingest_worker.get_settings", return_value=settings),
        patch(
            "platform_service.workers.ingest_worker.run_pipeline_for_source_job",
            new_callable=AsyncMock,
        ) as mock_pipeline,
        patch(
            "platform_service.workers.ingest_worker._merge_and_draft_batch",
            new_callable=AsyncMock,
        ) as mock_merge,
        patch(
            "platform_service.workers.ingest_worker.RunStateService",
            return_value=MagicMock(refresh_batch_status=AsyncMock()),
        ),
    ):
        await run_ingest_batch_job(payload)

    identify_job: IngestJob = mock_pipeline.await_args.args[0]
    assert identify_job.stop_after_identify is True
    mock_merge.assert_awaited_once_with(batch_id)


@pytest.mark.asyncio
async def test_merge_and_draft_binds_batch_tenant() -> None:
    """Candidate merge requires require_selected_tenant_id; bind from ingest_batch."""
    batch_id = uuid4()
    bound: list[int] = []

    async def capture_merge(_batch_id):
        bound.append(require_selected_tenant_id())
        return CandidateMergeSummary(
            input_candidate_count=0,
            group_count=0,
            merged_candidate_count=0,
            unmerged_candidate_count=0,
            skipped=True,
            succeeded=True,
        )

    with (
        patch(
            "platform_service.workers.ingest_worker.ingest_batch_tenant_id",
            new_callable=AsyncMock,
            return_value=42,
        ),
        patch(
            "platform_service.workers.ingest_worker.CandidateMergeRunner.run_staged",
            side_effect=capture_merge,
        ),
        patch(
            "platform_service.workers.ingest_worker._draft_jobs_for_batch",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        await _merge_and_draft_batch(batch_id)

    assert bound == [42]
