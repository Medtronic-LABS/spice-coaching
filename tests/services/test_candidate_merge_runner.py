"""Candidate merge runner: transactional replace and participating-run filter."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from platform_service.auth.tenant_context import using_selected_tenant
from platform_service.db.models.ingest_batch import IngestBatch
from platform_service.db.models.ingestion_run import IngestionRun, IngestionRunStep
from platform_service.db.models.module_candidate_draft import ModuleCandidateDraft
from platform_service.db.models.source_document import SourceDocument
from platform_service.services.candidate_merge_runner import CandidateMergeRunner
from platform_service.services.candidate_merger import CandidateMergerResult, MergeGroup
from platform_service.services.run_state_service import (
    RUN_FAILED,
    RUN_RUNNING,
    STAGE_CANDIDATE_MERGE,
    STAGE_MODULE_IDENTIFY,
    STEP_FAILED,
    STEP_SUCCEEDED,
)
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
            "TRUNCATE module_candidate_draft, ingestion_run_step, ingestion_run, "
            "ingest_batch, source_document RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()


async def _seed_doc(session: AsyncSession, *, title: str) -> SourceDocument:
    doc = SourceDocument(
        title=title,
        source_type="pdf",
        primary_language="en",
        content_domain="clinical",
        original_storage_path="/tmp/x.pdf",
        tenant_id=1,
    )
    session.add(doc)
    await session.flush()
    return doc


async def _seed_run(
    session: AsyncSession,
    *,
    batch: IngestBatch,
    doc: SourceDocument,
    status: str = RUN_RUNNING,
    identify_succeeded: bool = True,
    started_at: datetime | None = None,
) -> IngestionRun:
    run = IngestionRun(
        source_document_id=doc.id,
        ingest_batch_id=batch.id,
        status=status,
        started_at=started_at or datetime.now(UTC),
    )
    session.add(run)
    await session.flush()
    session.add(
        IngestionRunStep(
            ingestion_run_id=run.id,
            stage=STAGE_MODULE_IDENTIFY,
            status=STEP_SUCCEEDED if identify_succeeded else STEP_FAILED,
            started_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return run


async def _seed_candidate(
    session: AsyncSession,
    run: IngestionRun,
    doc: SourceDocument,
    *,
    title: str,
    chunk_id: str,
) -> ModuleCandidateDraft:
    cand = ModuleCandidateDraft(
        ingestion_run_id=run.id,
        proposed_title=title,
        scope_summary=f"Scope for {title}.",
        source_provenance_jsonb=[{"source_document_id": str(doc.id), "content_block_ids": []}],
        estimated_card_count=5,
        estimated_quiz_count=4,
        proposed_module_type="refresher",
        source_chunk_ids=[chunk_id],
        tenant_id=1,
    )
    session.add(cand)
    await session.flush()
    return cand


def _mock_merger(result: CandidateMergerResult) -> MagicMock:
    merger = MagicMock()
    merger.merge = AsyncMock(return_value=result)
    return merger


class TestCandidateMergeRunnerReplace:
    async def test_replaces_group_onto_home_run_keeps_unmerged(self, db_session: AsyncSession) -> None:
        batch = IngestBatch(status="running", tenant_id=1)
        db_session.add(batch)
        await db_session.flush()
        doc_a = await _seed_doc(db_session, title="a")
        doc_b = await _seed_doc(db_session, title="b")
        run_a = await _seed_run(
            db_session,
            batch=batch,
            doc=doc_a,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        run_b = await _seed_run(
            db_session,
            batch=batch,
            doc=doc_b,
            started_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        cand_a = await _seed_candidate(db_session, run_a, doc_a, title="ANC A", chunk_id="chunk-1")
        cand_b = await _seed_candidate(db_session, run_b, doc_b, title="ANC B", chunk_id="chunk-1")
        leftover = await _seed_candidate(db_session, run_b, doc_b, title="Diabetes", chunk_id="chunk-2")
        await db_session.commit()

        merger = _mock_merger(
            CandidateMergerResult(
                groups=[
                    MergeGroup(
                        constituent_ids=[cand_a.id, cand_b.id],
                        merged_title="ANC counselling",
                        merged_scope_summary="Unified ANC.",
                        pairing_rationale="Same topic.",
                    )
                ],
                unmerged_ids=[leftover.id],
                raw_response_text="",
            )
        )
        with using_selected_tenant(1):
            summary = await CandidateMergeRunner(db_session, merger=merger).run(batch.id)
            await db_session.commit()

        assert summary.group_count == 1
        assert summary.unmerged_candidate_count == 1
        remaining = (await db_session.execute(select(ModuleCandidateDraft))).scalars().all()
        remaining_ids = {c.id for c in remaining}
        assert cand_a.id not in remaining_ids
        assert cand_b.id not in remaining_ids
        assert leftover.id in remaining_ids
        merged = next(c for c in remaining if c.id != leftover.id)
        assert merged.ingestion_run_id == run_a.id
        assert merged.proposed_title == "ANC counselling"
        assert merged.source_chunk_ids == ["chunk-1"]
        flags = merged.quality_flags_jsonb or {}
        assert "topic_merged" in (flags.get("flags") or [])
        refs = (flags.get("merge_lineage") or {}).get("chunk_refs") or []
        assert {r["source_document_id"] for r in refs} == {str(doc_a.id), str(doc_b.id)}

        steps = (
            (
                await db_session.execute(
                    select(IngestionRunStep).where(IngestionRunStep.stage == STAGE_CANDIDATE_MERGE)
                )
            )
            .scalars()
            .all()
        )
        assert {s.ingestion_run_id for s in steps} == {run_a.id, run_b.id}
        assert all(s.status == STEP_SUCCEEDED for s in steps)

    async def test_omits_identify_failed_run(self, db_session: AsyncSession) -> None:
        batch = IngestBatch(status="running", tenant_id=1)
        db_session.add(batch)
        await db_session.flush()
        doc_ok = await _seed_doc(db_session, title="ok")
        doc_fail = await _seed_doc(db_session, title="fail")
        run_ok = await _seed_run(db_session, batch=batch, doc=doc_ok)
        await _seed_run(
            db_session,
            batch=batch,
            doc=doc_fail,
            status=RUN_FAILED,
            identify_succeeded=False,
        )
        cand = await _seed_candidate(db_session, run_ok, doc_ok, title="Only", chunk_id="chunk-1")
        await db_session.commit()

        merger = _mock_merger(
            CandidateMergerResult(
                groups=[],
                unmerged_ids=[cand.id],
                raw_response_text="",
            )
        )
        with using_selected_tenant(1):
            summary = await CandidateMergeRunner(db_session, merger=merger).run(batch.id)
            await db_session.commit()

        payloads = merger.merge.await_args.args[0]
        assert [p["id"] for p in payloads] == [cand.id]
        assert summary.input_candidate_count == 1
        leftover = await db_session.get(ModuleCandidateDraft, cand.id)
        assert leftover is not None
