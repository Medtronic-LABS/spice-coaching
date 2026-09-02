"""Tests for RunStateService post-publish finalization."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from mc_contracts.errors import ErrorCode
from platform_service.db.models.ingestion_run import IngestionRun
from platform_service.db.models.source_document import SourceDocument
from platform_service.services.run_state_service import (
    FUSION_RUN_TYPE,
    RUN_FAILED,
    RUN_PARTIALLY_SUCCEEDED,
    RUN_RUNNING,
    RUN_SUCCEEDED,
    STAGE_CARD_DRAFT,
    STAGE_GAP_CLASSIFICATION,
    STAGE_QUIZ_GENERATION,
    RunStateService,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _wipe(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text("TRUNCATE source_document, ingestion_run_step, ingestion_run RESTART IDENTITY CASCADE")
    )
    await db_session.commit()


async def _seed_run(session: AsyncSession) -> tuple[RunStateService, object]:
    sd = SourceDocument(
        title="t",
        source_type="pdf",
        primary_language="en",
        content_domain="clinical",
        original_storage_path="/tmp/x.pdf",
        tenant_id=1,
    )
    session.add(sd)
    await session.flush()
    run_state = RunStateService(session)
    run = await run_state.start_run(source_document_id=sd.id)
    await session.commit()
    return run_state, run


class TestMaybeFinalizeIngestionRun:
    async def test_no_post_publish_steps_finalizes_immediately(self, db_session: AsyncSession) -> None:
        run_state, run = await _seed_run(db_session)
        finalized = await run_state.maybe_finalize_ingestion_run(run.id)
        await db_session.commit()
        assert finalized is True
        row = await db_session.get(IngestionRun, run.id)
        assert row is not None
        assert row.status == RUN_SUCCEEDED

    async def test_pending_post_publish_keeps_run_running(self, db_session: AsyncSession) -> None:
        run_state, run = await _seed_run(db_session)
        await run_state.start_step(
            run_id=run.id,
            stage=STAGE_QUIZ_GENERATION,
            input_summary={"candidate_id": str(uuid4()), "module_id": str(uuid4())},
        )
        await run_state.start_step(
            run_id=run.id,
            stage=STAGE_GAP_CLASSIFICATION,
            input_summary={"candidate_id": str(uuid4()), "module_id": str(uuid4())},
        )
        await db_session.commit()

        finalized = await run_state.maybe_finalize_ingestion_run(run.id)
        await db_session.commit()
        assert finalized is False
        row = await db_session.get(IngestionRun, run.id)
        assert row is not None
        assert row.status == RUN_RUNNING

    async def test_all_post_publish_terminal_finalizes_succeeded(self, db_session: AsyncSession) -> None:
        run_state, run = await _seed_run(db_session)
        quiz = await run_state.start_step(
            run_id=run.id,
            stage=STAGE_QUIZ_GENERATION,
            input_summary={"candidate_id": str(uuid4()), "module_id": str(uuid4())},
        )
        gap = await run_state.start_step(
            run_id=run.id,
            stage=STAGE_GAP_CLASSIFICATION,
            input_summary={"candidate_id": str(uuid4()), "module_id": str(uuid4())},
        )
        await run_state.complete_step(quiz.id, output_summary={"questions_written": 3})
        await run_state.complete_step(gap.id, output_summary={"secondary_links_written": 1})
        await db_session.commit()

        finalized = await run_state.maybe_finalize_ingestion_run(run.id)
        await db_session.commit()
        assert finalized is True
        row = await db_session.get(IngestionRun, run.id)
        assert row is not None
        assert row.status == RUN_SUCCEEDED

    async def test_failed_post_publish_partially_succeeds(self, db_session: AsyncSession) -> None:
        run_state, run = await _seed_run(db_session)
        quiz = await run_state.start_step(
            run_id=run.id,
            stage=STAGE_QUIZ_GENERATION,
            input_summary={"candidate_id": str(uuid4()), "module_id": str(uuid4())},
        )
        gap = await run_state.start_step(
            run_id=run.id,
            stage=STAGE_GAP_CLASSIFICATION,
            input_summary={"candidate_id": str(uuid4()), "module_id": str(uuid4())},
        )
        await run_state.fail_step(
            quiz.id,
            error_code=ErrorCode.GENERATION_FAILED.value,
            error_message="boom",
            error={"type": "TestError", "message": "boom"},
        )
        await db_session.refresh(quiz)
        assert quiz.error_code == ErrorCode.GENERATION_FAILED.value
        assert quiz.error_message == "boom"
        await run_state.complete_step(gap.id, output_summary={"secondary_links_written": 0})
        await db_session.commit()

        await run_state.maybe_finalize_ingestion_run(run.id)
        await db_session.commit()
        row = await db_session.get(IngestionRun, run.id)
        assert row is not None
        assert row.status == RUN_PARTIALLY_SUCCEEDED
        assert STAGE_QUIZ_GENERATION in (row.error_jsonb or {}).get("failed_stages", [])
        assert "Generating quiz" in (row.error_jsonb or {}).get("message", "")

    async def test_skipped_quiz_counts_as_terminal(self, db_session: AsyncSession) -> None:
        run_state, run = await _seed_run(db_session)
        await run_state.skip_step(
            run_id=run.id,
            stage=STAGE_QUIZ_GENERATION,
            reason="assessment_mode_read_only",
            input_summary={"candidate_id": str(uuid4()), "module_id": str(uuid4())},
        )
        gap = await run_state.start_step(
            run_id=run.id,
            stage=STAGE_GAP_CLASSIFICATION,
            input_summary={"candidate_id": str(uuid4()), "module_id": str(uuid4())},
        )
        await run_state.complete_step(gap.id, output_summary={"secondary_links_written": 0})
        await db_session.commit()

        await run_state.maybe_finalize_ingestion_run(run.id)
        await db_session.commit()
        row = await db_session.get(IngestionRun, run.id)
        assert row is not None
        assert row.status == RUN_SUCCEEDED

    async def test_failed_card_draft_included_in_finalize(self, db_session: AsyncSession) -> None:
        run_state, run = await _seed_run(db_session)
        card = await run_state.start_step(
            run_id=run.id,
            stage=STAGE_CARD_DRAFT,
            input_summary={"candidate_id": str(uuid4())},
        )
        await run_state.fail_step(
            card.id,
            error_code=ErrorCode.DRAFT_FAILED.value,
            error_message="draft failed",
            error={"type": "RuntimeError", "message": "draft failed"},
        )
        await run_state.skip_step(
            run_id=run.id,
            stage=STAGE_QUIZ_GENERATION,
            reason="assessment_mode_read_only",
            input_summary={"candidate_id": str(uuid4()), "module_id": str(uuid4())},
        )
        gap = await run_state.start_step(
            run_id=run.id,
            stage=STAGE_GAP_CLASSIFICATION,
            input_summary={"candidate_id": str(uuid4()), "module_id": str(uuid4())},
        )
        await run_state.complete_step(gap.id, output_summary={"secondary_links_written": 0})
        await db_session.commit()

        await run_state.maybe_finalize_ingestion_run(run.id)
        await db_session.commit()
        row = await db_session.get(IngestionRun, run.id)
        assert row is not None
        assert row.status == RUN_PARTIALLY_SUCCEEDED
        assert row.error_jsonb is not None
        assert row.error_jsonb.get("draft_failures") == 1
        assert "Card drafting failed" in (row.error_jsonb.get("message") or "")


class TestFusionRunLookup:
    async def test_find_active_fusion_run_for_document(self, db_session: AsyncSession) -> None:
        sd1 = SourceDocument(
            title="a",
            source_type="pdf",
            primary_language="en",
            content_domain="clinical",
            original_storage_path="/tmp/a.pdf",
            tenant_id=1,
        )
        sd2 = SourceDocument(
            title="b",
            source_type="pdf",
            primary_language="en",
            content_domain="clinical",
            original_storage_path="/tmp/b.pdf",
            tenant_id=1,
        )
        db_session.add_all([sd1, sd2])
        await db_session.flush()
        fusion_run = IngestionRun(
            source_document_id=sd1.id,
            status=RUN_RUNNING,
            error_jsonb={
                "type": FUSION_RUN_TYPE,
                "source_document_ids": [str(sd1.id), str(sd2.id)],
            },
        )
        db_session.add(fusion_run)
        await db_session.commit()

        run_state = RunStateService(db_session)
        found = await run_state.find_active_fusion_run_for_document(sd2.id)
        assert found is not None
        assert found.id == fusion_run.id


class TestPatchStepInputSummary:
    async def test_merges_activity_into_input_summary(self, db_session: AsyncSession) -> None:
        run_state, run = await _seed_run(db_session)
        step = await run_state.start_step(
            run_id=run.id,
            stage=STAGE_CARD_DRAFT,
            input_summary={"candidate_id": str(uuid4())},
        )
        await run_state.patch_step_input_summary(
            step.id,
            {"activity": "published_module_merge"},
        )
        await db_session.commit()
        await db_session.refresh(step)
        assert step.input_summary_jsonb is not None
        assert step.input_summary_jsonb.get("activity") == "published_module_merge"
        assert "candidate_id" in step.input_summary_jsonb


class TestCompleteRunMarksSourceFailed:
    async def test_partially_succeeded_marks_source_partially_succeeded(
        self, db_session: AsyncSession
    ) -> None:
        run_state, run = await _seed_run(db_session)
        sd = await db_session.get(SourceDocument, run.source_document_id)
        assert sd is not None
        sd.status = "ingesting"
        await db_session.commit()

        await run_state.complete_run(
            run.id,
            status=RUN_PARTIALLY_SUCCEEDED,
            error_jsonb={"failed_stage": "module_identify"},
        )
        await db_session.commit()
        await db_session.refresh(sd)
        assert sd.status == "partially_succeeded"

    async def test_failed_marks_ingesting_source_failed(self, db_session: AsyncSession) -> None:
        run_state, run = await _seed_run(db_session)
        sd = await db_session.get(SourceDocument, run.source_document_id)
        assert sd is not None
        sd.status = "ingesting"
        await db_session.commit()

        await run_state.complete_run(run.id, status=RUN_FAILED, error_jsonb={"code": "extract_failed"})
        await db_session.commit()
        await db_session.refresh(sd)
        assert sd.status == "failed"

    async def test_succeeded_marks_ingesting_source_ingested(self, db_session: AsyncSession) -> None:
        run_state, run = await _seed_run(db_session)
        sd = await db_session.get(SourceDocument, run.source_document_id)
        assert sd is not None
        sd.status = "ingesting"
        await db_session.commit()

        await run_state.complete_run(run.id, status=RUN_SUCCEEDED)
        await db_session.commit()
        await db_session.refresh(sd)
        assert sd.status == "ingested"

    async def test_skips_retired_source_documents(self, db_session: AsyncSession) -> None:
        run_state, run = await _seed_run(db_session)
        sd = await db_session.get(SourceDocument, run.source_document_id)
        assert sd is not None
        sd.status = "retired"
        await db_session.commit()

        await run_state.complete_run(run.id, status=RUN_FAILED, error_jsonb={"code": "extract_failed"})
        await db_session.commit()
        await db_session.refresh(sd)
        assert sd.status == "retired"

    async def test_fusion_run_failure_preserves_source_documents_status(
        self, db_session: AsyncSession
    ) -> None:
        sd_a = SourceDocument(
            title="a",
            source_type="pdf",
            primary_language="en",
            content_domain="clinical",
            original_storage_path="/tmp/a.pdf",
            status="ingested",
            tenant_id=1,
        )
        sd_b = SourceDocument(
            title="b",
            source_type="pdf",
            primary_language="en",
            content_domain="clinical",
            original_storage_path="/tmp/b.pdf",
            status="ingested",
            tenant_id=1,
        )
        db_session.add_all([sd_a, sd_b])
        await db_session.flush()
        run_state = RunStateService(db_session)
        fusion_run = await run_state.start_fusion_run(source_document_ids=[sd_a.id, sd_b.id])
        await db_session.commit()

        await run_state.complete_run(fusion_run.id, status=RUN_FAILED)
        await db_session.commit()
        await db_session.refresh(sd_a)
        await db_session.refresh(sd_b)
        assert sd_a.status == "ingested"
        assert sd_b.status == "ingested"
