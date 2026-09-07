"""Tests for post-publish step creation on Stage D enqueue."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from platform_service.db.models.ingestion_run import IngestionRun, IngestionRunStep
from platform_service.db.models.module_candidate_draft import ModuleCandidateDraft
from platform_service.db.models.source_document import SourceDocument
from platform_service.services.run_state_service import (
    RUN_RUNNING,
    STAGE_GAP_CLASSIFICATION,
    STAGE_QUIZ_GENERATION,
    STAGE_TRIGGER_BINDING,
    STEP_SKIPPED,
    RunStateService,
)
from platform_service.workers.stage_d_draft import StageDOrchestrator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _wipe(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text(
            "TRUNCATE module, module_family, module_candidate_draft, source_document, "
            "ingestion_run_step, ingestion_run, ingest_batch RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()


async def _seed_run_and_candidate(
    session: AsyncSession,
    *,
    assessment_mode: str = "with_quiz",
    quizzes_per_module: int | None = None,
) -> tuple[StageDOrchestrator, IngestionRun, ModuleCandidateDraft, SourceDocument]:
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
    batch = await run_state.create_batch(
        assessment_mode=assessment_mode,
        quizzes_per_module=quizzes_per_module,
    )
    run = await run_state.start_run(source_document_id=sd.id, ingest_batch_id=batch.id)
    cand = ModuleCandidateDraft(
        ingestion_run_id=run.id,
        proposed_title="T",
        scope_summary="x",
        source_provenance_jsonb=[{"source_document_id": str(sd.id), "content_block_ids": []}],
        estimated_card_count=5,
        estimated_quiz_count=4,
        proposed_module_type="refresher",
        tenant_id=1,
    )
    session.add(cand)
    await session.flush()
    return StageDOrchestrator(session), run, cand, sd


class TestEnqueuePostPublishSteps:
    async def test_creates_quiz_and_gap_steps_only(self, db_session: AsyncSession) -> None:
        stage_d, run, cand, sd = await _seed_run_and_candidate(db_session)
        module_id = uuid4()
        mock_quiz = MagicMock()
        mock_gap = MagicMock()
        mock_trigger = MagicMock()

        with (
            patch("platform_service.services.draft_pipeline.enqueue_module_quiz", mock_quiz),
            patch("platform_service.services.draft_pipeline.enqueue_classify_module_gaps", mock_gap),
            patch(
                "platform_service.services.draft_pipeline.enqueue_bind_assessment_triggers",
                mock_trigger,
            ),
        ):
            await stage_d._enqueue_post_publish(
                module_id,
                [sd.id],
                ingestion_run_id=run.id,
                candidate_id=cand.id,
            )

        steps = list(
            (
                await db_session.execute(
                    select(IngestionRunStep).where(IngestionRunStep.ingestion_run_id == run.id)
                )
            ).scalars()
        )
        stages = {s.stage: s for s in steps}
        assert STAGE_QUIZ_GENERATION in stages
        assert STAGE_GAP_CLASSIFICATION in stages
        assert STAGE_TRIGGER_BINDING not in stages
        assert stages[STAGE_QUIZ_GENERATION].status == "running"
        mock_quiz.assert_called_once()
        mock_gap.assert_called_once()
        mock_trigger.assert_not_called()

    async def test_passes_quiz_size_when_batch_has_target(
        self,
        db_session: AsyncSession,
    ) -> None:
        stage_d, run, cand, sd = await _seed_run_and_candidate(
            db_session,
            quizzes_per_module=6,
        )
        cand.estimated_quiz_count = 6
        await db_session.flush()
        module_id = uuid4()
        mock_quiz = MagicMock()
        mock_gap = MagicMock()

        with (
            patch("platform_service.services.draft_pipeline.enqueue_module_quiz", mock_quiz),
            patch("platform_service.services.draft_pipeline.enqueue_classify_module_gaps", mock_gap),
        ):
            await stage_d._enqueue_post_publish(
                module_id,
                [sd.id],
                ingestion_run_id=run.id,
                candidate_id=cand.id,
            )

        mock_quiz.assert_called_once()
        assert mock_quiz.call_args.kwargs.get("quiz_size") == 6

        run_row = await db_session.get(IngestionRun, run.id)
        assert run_row is not None
        assert run_row.status == RUN_RUNNING

    async def test_read_only_skips_quiz_step(self, db_session: AsyncSession) -> None:
        stage_d, run, cand, sd = await _seed_run_and_candidate(db_session, assessment_mode="read_only")
        module_id = uuid4()
        mock_quiz = MagicMock()
        mock_gap = MagicMock()

        with (
            patch("platform_service.services.draft_pipeline.enqueue_module_quiz", mock_quiz),
            patch("platform_service.services.draft_pipeline.enqueue_classify_module_gaps", mock_gap),
        ):
            await stage_d._enqueue_post_publish(
                module_id,
                [sd.id],
                ingestion_run_id=run.id,
                candidate_id=cand.id,
            )

        steps = list(
            (
                await db_session.execute(
                    select(IngestionRunStep).where(IngestionRunStep.ingestion_run_id == run.id)
                )
            ).scalars()
        )
        quiz_steps = [s for s in steps if s.stage == STAGE_QUIZ_GENERATION]
        assert len(quiz_steps) == 1
        assert quiz_steps[0].status == STEP_SKIPPED
        mock_quiz.assert_not_called()
        mock_gap.assert_called_once()
