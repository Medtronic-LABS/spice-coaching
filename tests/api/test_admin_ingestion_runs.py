"""Admin ingestion-run API tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from platform_service.db.models.ingest_batch import IngestBatch
from platform_service.db.models.ingestion_run import IngestionRun, IngestionRunStep
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
from platform_service.db.models.source_document import SourceDocument
from platform_service.services.ingestion_run_generation_counts import (
    IngestionRunGenerationCountsService,
)
from platform_service.services.run_state.constants import FUSION_RUN_TYPE
from platform_service.services.run_state_service import STAGE_CARD_DRAFT
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import _seed_module
from tests.conftest import platform_path, requires_db
from tests.helpers.hierarchy_fixtures import AM_ID, PO_ID, seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]


class TestIngestionRunEndpoints:
    async def _seed_run(
        self,
        session: AsyncSession,
        *,
        status: str = "succeeded",
        started_offset_seconds: int = 0,
        completed_offset_seconds: int | None = None,
        title: str | None = None,
        original_filename: str | None = None,
        ingested_by: int | None = None,
        ingest_batch_id: UUID | None = None,
        error_jsonb: dict[str, object] | None = None,
        source_document_id: UUID | None = None,
    ) -> IngestionRun:
        # Need a source_document for the FK.
        if source_document_id is None:
            sd = SourceDocument(
                title=title or f"doc-{uuid4().hex[:6]}",
                source_type="pdf",
                primary_language="en",
                content_domain="clinical",
                original_storage_path="/tmp/test.pdf",
                original_filename=original_filename,
                tenant_id=1,
            )
            session.add(sd)
            await session.flush()
            source_document_id = sd.id
        started_at = datetime.now(UTC) + timedelta(seconds=started_offset_seconds)
        if status == "running":
            completed_at = None
        elif completed_offset_seconds is not None:
            completed_at = started_at + timedelta(seconds=completed_offset_seconds)
        else:
            completed_at = datetime.now(UTC)
        run = IngestionRun(
            source_document_id=source_document_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            ingested_by=ingested_by,
            ingest_batch_id=ingest_batch_id,
            error_jsonb=error_jsonb,
        )
        session.add(run)
        await session.flush()
        await session.commit()
        return run

    async def _add_card_draft_step(
        self,
        session: AsyncSession,
        run: IngestionRun,
        *,
        module_id: str | None,
        secondary_module_id: str | None = None,
        was_published_merge: bool | None = None,
    ) -> None:
        output_summary: dict[str, object] = {"module_id": module_id}
        if secondary_module_id is not None:
            output_summary["secondary_module_id"] = secondary_module_id
        if was_published_merge is not None:
            output_summary["was_published_merge"] = was_published_merge
        session.add(
            IngestionRunStep(
                ingestion_run_id=run.id,
                stage=STAGE_CARD_DRAFT,
                status="succeeded",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                output_summary_jsonb=output_summary,
            )
        )
        await session.commit()

    async def _freeze_counts(self, session: AsyncSession, run: IngestionRun) -> None:
        await IngestionRunGenerationCountsService(session).upsert_for_run(run.id)
        await session.commit()

    async def test_list_orders_by_started_desc(self, client: AsyncClient, db_session: AsyncSession) -> None:
        r1 = await self._seed_run(db_session, started_offset_seconds=0)
        r2 = await self._seed_run(db_session, started_offset_seconds=10)
        r3 = await self._seed_run(db_session, started_offset_seconds=20)

        resp = await client.get(platform_path("/admin/ingestion-runs"))
        body = resp.json()
        ids = [row["id"] for row in body["runs"]]
        # Newest-first.
        assert ids == [str(r3.id), str(r2.id), str(r1.id)]
        assert body["total_runs"] == 3

    async def test_list_shows_only_latest_run_per_source_document(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        older = await self._seed_run(db_session, started_offset_seconds=0, title="shared-doc")
        newer = await self._seed_run(
            db_session,
            started_offset_seconds=30,
            source_document_id=older.source_document_id,
            title="shared-doc",
        )
        other = await self._seed_run(db_session, started_offset_seconds=10, title="other-doc")

        resp = await client.get(platform_path("/admin/ingestion-runs"))
        assert resp.status_code == 200
        body = resp.json()
        ids = {row["id"] for row in body["runs"]}
        assert ids == {str(newer.id), str(other.id)}
        assert str(older.id) not in ids
        assert body["total_runs"] == 2

        detail = await client.get(platform_path(f"/admin/ingestion-runs/{older.id}"))
        assert detail.status_code == 200
        assert detail.json()["id"] == str(older.id)

    async def test_list_filters_by_status(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_run(db_session, status="succeeded", started_offset_seconds=0)
        await self._seed_run(db_session, status="failed", started_offset_seconds=10)

        resp = await client.get(platform_path("/admin/ingestion-runs?status=failed"))
        body = resp.json()
        statuses = {row["status"] for row in body["runs"]}
        assert statuses == {"failed"}
        assert body["total_runs"] == 1

    async def test_filename_query(self, client: AsyncClient, db_session: AsyncSession) -> None:
        match = await self._seed_run(
            db_session,
            title="other-title",
            original_filename="Hypertension_Training.mp4",
            started_offset_seconds=0,
        )
        await self._seed_run(
            db_session,
            title="unrelated",
            original_filename="Diabetes_Overview.mp4",
            started_offset_seconds=10,
        )

        resp = await client.get(platform_path("/admin/ingestion-runs?q=hyper"))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["runs"]) == 1
        assert body["runs"][0]["id"] == str(match.id)
        assert body["runs"][0]["document_label"] == "Hypertension_Training.mp4"
        assert body["total_runs"] == 1

    async def test_filename_query_matches_title(self, client: AsyncClient, db_session: AsyncSession) -> None:
        run = await self._seed_run(
            db_session,
            title="BRAC Counselling Video",
            original_filename="clip-001.mp4",
            started_offset_seconds=0,
        )

        resp = await client.get(platform_path("/admin/ingestion-runs?q=counselling"))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["runs"]) == 1
        assert body["runs"][0]["id"] == str(run.id)
        assert body["runs"][0]["document_label"] == "clip-001.mp4"

    async def test_filename_query_combines_with_status(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        match = await self._seed_run(
            db_session,
            title="Hypertension Guide",
            original_filename="hypertension.pdf",
            status="failed",
            started_offset_seconds=0,
        )
        await self._seed_run(
            db_session,
            title="Hypertension Overview",
            original_filename="hypertension-v2.pdf",
            status="succeeded",
            started_offset_seconds=10,
        )

        resp = await client.get(platform_path("/admin/ingestion-runs?q=hypertension&status=failed"))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["runs"]) == 1
        assert body["runs"][0]["id"] == str(match.id)
        assert body["total_runs"] == 1

    async def test_pagination_limit_offset(self, client: AsyncClient, db_session: AsyncSession) -> None:
        for i in range(5):
            await self._seed_run(db_session, started_offset_seconds=i)

        resp = await client.get(platform_path("/admin/ingestion-runs?limit=2&offset=0"))
        body = resp.json()
        assert len(body["runs"]) == 2
        assert body["total_runs"] == 5
        assert body["total_pages"] == 3
        assert body["limit"] == 2
        assert body["offset"] == 0

        resp = await client.get(platform_path("/admin/ingestion-runs?limit=2&offset=2"))
        body = resp.json()
        assert len(body["runs"]) == 2
        assert body["total_runs"] == 5
        assert body["offset"] == 2

        resp = await client.get(platform_path("/admin/ingestion-runs?limit=2&offset=4"))
        body = resp.json()
        assert len(body["runs"]) == 1
        assert body["total_runs"] == 5

    async def test_limit_validation_rejects_zero(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/ingestion-runs?limit=0"))
        assert resp.status_code == 422

    async def test_limit_validation_rejects_excessive(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/ingestion-runs?limit=500"))
        assert resp.status_code == 422

    async def test_list_orders_by_started_asc(self, client: AsyncClient, db_session: AsyncSession) -> None:
        r1 = await self._seed_run(db_session, started_offset_seconds=0)
        r2 = await self._seed_run(db_session, started_offset_seconds=10)
        r3 = await self._seed_run(db_session, started_offset_seconds=20)

        resp = await client.get(platform_path("/admin/ingestion-runs?sort_by=started_at&sort_dir=asc"))
        body = resp.json()
        ids = [row["id"] for row in body["runs"]]
        assert ids == [str(r1.id), str(r2.id), str(r3.id)]

    async def test_list_orders_by_status_asc(self, client: AsyncClient, db_session: AsyncSession) -> None:
        failed = await self._seed_run(db_session, status="failed", started_offset_seconds=0)
        running = await self._seed_run(db_session, status="running", started_offset_seconds=10)
        succeeded = await self._seed_run(db_session, status="succeeded", started_offset_seconds=20)

        resp = await client.get(platform_path("/admin/ingestion-runs?sort_by=status&sort_dir=asc"))
        body = resp.json()
        ids = [row["id"] for row in body["runs"]]
        assert ids == [str(failed.id), str(running.id), str(succeeded.id)]

    async def test_list_orders_by_completed_desc_nulls_last(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        early = await self._seed_run(
            db_session,
            status="succeeded",
            started_offset_seconds=0,
            completed_offset_seconds=10,
        )
        late = await self._seed_run(
            db_session,
            status="succeeded",
            started_offset_seconds=100,
            completed_offset_seconds=50,
        )
        in_progress = await self._seed_run(db_session, status="running", started_offset_seconds=200)

        resp = await client.get(platform_path("/admin/ingestion-runs?sort_by=completed_at&sort_dir=desc"))
        body = resp.json()
        ids = [row["id"] for row in body["runs"]]
        assert ids == [str(late.id), str(early.id), str(in_progress.id)]

    async def test_list_orders_by_document_label_asc(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        alpha = await self._seed_run(
            db_session,
            original_filename="alpha.pdf",
            title="Alpha Title",
            started_offset_seconds=0,
        )
        beta = await self._seed_run(
            db_session,
            original_filename="beta.pdf",
            title="Beta Title",
            started_offset_seconds=10,
        )
        charlie = await self._seed_run(
            db_session,
            title="Charlie Title",
            original_filename=None,
            started_offset_seconds=20,
        )

        resp = await client.get(platform_path("/admin/ingestion-runs?sort_by=document_label&sort_dir=asc"))
        body = resp.json()
        ids = [row["id"] for row in body["runs"]]
        assert ids == [str(alpha.id), str(beta.id), str(charlie.id)]

    async def test_sort_by_validation_rejects_invalid(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/ingestion-runs?sort_by=invalid"))
        assert resp.status_code == 422

    async def test_sort_dir_validation_rejects_invalid(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/ingestion-runs?sort_dir=up"))
        assert resp.status_code == 422

    async def test_list_includes_document_label_and_generated_counts(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        run = await self._seed_run(
            db_session,
            title="Guideline Title",
            original_filename="uhis-q1.pdf",
        )
        m1 = await _seed_module(
            db_session,
            module_json={
                "cards": [
                    {"title": {"bn": "1"}, "body": {"bn": "a"}},
                    {"title": {"bn": "2"}, "body": {"bn": "b"}},
                    {"title": {"bn": "3"}, "body": {"bn": "c"}},
                ]
            },
        )
        m2 = await _seed_module(
            db_session,
            module_json={
                "cards": [
                    {"title": {"bn": "4"}, "body": {"bn": "d"}},
                    {"title": {"bn": "5"}, "body": {"bn": "e"}},
                ]
            },
        )
        db_session.add(
            ModuleQuizQuestion(
                module_id=m1.id,
                question_order=1,
                question_family_id=uuid4(),
                question_version=1,
                question_localized={"bn": "Q1"},
                question_type="single_select",
                options_localized={"bn": ["a", "b", "c", "d"]},
                correct_indices=[0],
            )
        )
        db_session.add(
            ModuleQuizQuestion(
                module_id=m1.id,
                question_order=2,
                question_family_id=uuid4(),
                question_version=1,
                question_localized={"bn": "Q2"},
                question_type="single_select",
                options_localized={"bn": ["a", "b", "c", "d"]},
                correct_indices=[1],
            )
        )
        db_session.add(
            ModuleQuizQuestion(
                module_id=m2.id,
                question_order=1,
                question_family_id=uuid4(),
                question_version=1,
                question_localized={"bn": "Q3"},
                question_type="single_select",
                options_localized={"bn": ["a", "b", "c", "d"]},
                correct_indices=[0],
            )
        )
        await db_session.commit()

        await self._add_card_draft_step(db_session, run, module_id=str(m1.id))
        await self._add_card_draft_step(db_session, run, module_id=str(m2.id))
        # Duplicate module_id (retry) must not double-count.
        await self._add_card_draft_step(db_session, run, module_id=str(m1.id))
        await self._add_card_draft_step(db_session, run, module_id=None)
        await self._freeze_counts(db_session, run)

        resp = await client.get(platform_path("/admin/ingestion-runs"))
        assert resp.status_code == 200
        row = next(r for r in resp.json()["runs"] if r["id"] == str(run.id))
        assert row["document_label"] == "uhis-q1.pdf"
        assert row["generated_module_count"] == 2
        assert row["generated_card_count"] == 5
        assert row["generated_quiz_count"] == 3

    async def test_list_document_label_falls_back_to_title(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        run = await self._seed_run(
            db_session,
            title="Fallback Doc Title",
            original_filename=None,
        )
        resp = await client.get(platform_path("/admin/ingestion-runs"))
        row = next(r for r in resp.json()["runs"] if r["id"] == str(run.id))
        assert row["document_label"] == "Fallback Doc Title"
        assert row["generated_module_count"] == 0
        assert row["generated_card_count"] == 0
        assert row["generated_quiz_count"] == 0

    async def test_list_zeros_counts_without_frozen_snapshot(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Live card_draft modules must not leak into list without a snapshot."""
        run = await self._seed_run(
            db_session,
            status="failed",
            original_filename="failed-run.pdf",
        )
        module = await _seed_module(
            db_session,
            module_json={
                "cards": [
                    {"title": {"bn": "1"}, "body": {"bn": "a"}},
                    {"title": {"bn": "2"}, "body": {"bn": "b"}},
                ]
            },
        )
        await self._add_card_draft_step(db_session, run, module_id=str(module.id))

        resp = await client.get(platform_path("/admin/ingestion-runs?status=failed"))
        row = next(r for r in resp.json()["runs"] if r["id"] == str(run.id))
        assert row["document_label"] == "failed-run.pdf"
        assert row["generated_module_count"] == 0
        assert row["generated_card_count"] == 0
        assert row["generated_quiz_count"] == 0

    async def test_list_partially_succeeded_uses_frozen_snapshot(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        run = await self._seed_run(
            db_session,
            status="partially_succeeded",
            original_filename="partial.pdf",
        )
        module = await _seed_module(
            db_session,
            module_json={
                "cards": [
                    {"title": {"bn": "1"}, "body": {"bn": "a"}},
                    {"title": {"bn": "2"}, "body": {"bn": "b"}},
                ]
            },
        )
        await self._add_card_draft_step(db_session, run, module_id=str(module.id))
        await self._freeze_counts(db_session, run)

        resp = await client.get(platform_path("/admin/ingestion-runs?status=partially_succeeded"))
        row = next(r for r in resp.json()["runs"] if r["id"] == str(run.id))
        assert row["generated_module_count"] == 1
        assert row["generated_card_count"] == 2
        assert row["generated_quiz_count"] == 0

    async def test_detail_includes_steps_in_order(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        run = await self._seed_run(db_session)
        # Add three steps with increasing started_at.
        for i, stage in enumerate(("extract", "module_identify", "card_draft")):
            db_session.add(
                IngestionRunStep(
                    ingestion_run_id=run.id,
                    stage=stage,
                    status="succeeded",
                    started_at=datetime.now(UTC) + timedelta(seconds=i),
                    completed_at=datetime.now(UTC) + timedelta(seconds=i + 1),
                )
            )
        await db_session.commit()

        resp = await client.get(platform_path(f"/admin/ingestion-runs/{run.id}"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(run.id)
        stages = [s["stage"] for s in data["steps"]]
        assert stages == ["extract", "module_identify", "card_draft"]

    async def test_detail_includes_document_label_and_generated_counts(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        run = await self._seed_run(
            db_session,
            title="Detail Doc",
            original_filename="detail.pdf",
        )
        module = await _seed_module(
            db_session,
            module_json={
                "cards": [
                    {"title": {"bn": "1"}, "body": {"bn": "a"}},
                    {"title": {"bn": "2"}, "body": {"bn": "b"}},
                    {"title": {"bn": "3"}, "body": {"bn": "c"}},
                    {"title": {"bn": "4"}, "body": {"bn": "d"}},
                ]
            },
        )
        db_session.add(
            ModuleQuizQuestion(
                module_id=module.id,
                question_order=1,
                question_family_id=uuid4(),
                question_version=1,
                question_localized={"bn": "Q"},
                question_type="single_select",
                options_localized={"bn": ["a", "b", "c", "d"]},
                correct_indices=[0],
            )
        )
        await db_session.commit()
        await self._add_card_draft_step(db_session, run, module_id=str(module.id))
        await self._freeze_counts(db_session, run)

        resp = await client.get(platform_path(f"/admin/ingestion-runs/{run.id}"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_label"] == "detail.pdf"
        assert data["generated_module_count"] == 1
        assert data["generated_card_count"] == 4
        assert data["generated_quiz_count"] == 1

    async def test_list_and_detail_count_dual_path_merge_as_one_module(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        run = await self._seed_run(
            db_session,
            title="Merge Doc",
            original_filename="merge.pdf",
        )
        primary = await _seed_module(
            db_session,
            lifecycle_status="review_pending",
            module_json={
                "cards": [
                    {"title": {"bn": "1"}, "body": {"bn": "a"}},
                    {"title": {"bn": "2"}, "body": {"bn": "b"}},
                    {"title": {"bn": "3"}, "body": {"bn": "c"}},
                ]
            },
        )
        secondary = await _seed_module(
            db_session,
            lifecycle_status="review_pending",
            module_json={
                "cards": [
                    {"title": {"bn": "4"}, "body": {"bn": "d"}},
                    {"title": {"bn": "5"}, "body": {"bn": "e"}},
                    {"title": {"bn": "6"}, "body": {"bn": "f"}},
                    {"title": {"bn": "7"}, "body": {"bn": "g"}},
                ]
            },
        )
        db_session.add(
            ModuleQuizQuestion(
                module_id=primary.id,
                question_order=1,
                question_family_id=uuid4(),
                question_version=1,
                question_localized={"bn": "P1"},
                question_type="single_select",
                options_localized={"bn": ["a", "b", "c", "d"]},
                correct_indices=[0],
            )
        )
        db_session.add(
            ModuleQuizQuestion(
                module_id=primary.id,
                question_order=2,
                question_family_id=uuid4(),
                question_version=1,
                question_localized={"bn": "P2"},
                question_type="single_select",
                options_localized={"bn": ["a", "b", "c", "d"]},
                correct_indices=[1],
            )
        )
        db_session.add(
            ModuleQuizQuestion(
                module_id=secondary.id,
                question_order=1,
                question_family_id=uuid4(),
                question_version=1,
                question_localized={"bn": "S1"},
                question_type="single_select",
                options_localized={"bn": ["a", "b", "c", "d"]},
                correct_indices=[0],
            )
        )
        await db_session.commit()
        await self._add_card_draft_step(
            db_session,
            run,
            module_id=str(primary.id),
            secondary_module_id=str(secondary.id),
            was_published_merge=True,
        )
        await self._freeze_counts(db_session, run)

        list_resp = await client.get(platform_path("/admin/ingestion-runs"))
        assert list_resp.status_code == 200
        row = next(r for r in list_resp.json()["runs"] if r["id"] == str(run.id))
        assert row["generated_module_count"] == 1
        assert row["generated_card_count"] == 3
        assert row["generated_quiz_count"] == 2

        detail_resp = await client.get(platform_path(f"/admin/ingestion-runs/{run.id}"))
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["generated_module_count"] == 1
        assert detail["generated_card_count"] == 3
        assert detail["generated_quiz_count"] == 2

    async def test_list_excludes_secondary_module_id_on_second_card_draft_step(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        run = await self._seed_run(
            db_session,
            title="Merge Retry Doc",
            original_filename="merge-retry.pdf",
        )
        primary = await _seed_module(
            db_session,
            lifecycle_status="review_pending",
            module_json={
                "cards": [
                    {"title": {"bn": "1"}, "body": {"bn": "a"}},
                    {"title": {"bn": "2"}, "body": {"bn": "b"}},
                ]
            },
        )
        secondary = await _seed_module(
            db_session,
            lifecycle_status="review_pending",
            module_json={
                "cards": [
                    {"title": {"bn": "3"}, "body": {"bn": "c"}},
                    {"title": {"bn": "4"}, "body": {"bn": "d"}},
                    {"title": {"bn": "5"}, "body": {"bn": "e"}},
                ]
            },
        )
        db_session.add(
            ModuleQuizQuestion(
                module_id=primary.id,
                question_order=1,
                question_family_id=uuid4(),
                question_version=1,
                question_localized={"bn": "P"},
                question_type="single_select",
                options_localized={"bn": ["a", "b", "c", "d"]},
                correct_indices=[0],
            )
        )
        db_session.add(
            ModuleQuizQuestion(
                module_id=secondary.id,
                question_order=1,
                question_family_id=uuid4(),
                question_version=1,
                question_localized={"bn": "S"},
                question_type="single_select",
                options_localized={"bn": ["a", "b", "c", "d"]},
                correct_indices=[0],
            )
        )
        await db_session.commit()
        await self._add_card_draft_step(
            db_session,
            run,
            module_id=str(primary.id),
            secondary_module_id=str(secondary.id),
            was_published_merge=True,
        )
        # A second card_draft whose module_id is the secondary must not double-count.
        await self._add_card_draft_step(db_session, run, module_id=str(secondary.id))
        await self._freeze_counts(db_session, run)

        resp = await client.get(platform_path("/admin/ingestion-runs"))
        assert resp.status_code == 200
        row = next(r for r in resp.json()["runs"] if r["id"] == str(run.id))
        assert row["generated_module_count"] == 1
        assert row["generated_card_count"] == 2
        assert row["generated_quiz_count"] == 1

    async def test_fusion_shared_module_refreshes_sibling_pipeline_rows(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        batch = IngestBatch(status="running", assessment_mode="with_quiz", tenant_id=1)
        db_session.add(batch)
        await db_session.flush()

        run_a = await self._seed_run(
            db_session,
            original_filename="doc-a.pdf",
            ingest_batch_id=batch.id,
            started_offset_seconds=0,
        )
        run_b = await self._seed_run(
            db_session,
            original_filename="doc-b.pdf",
            ingest_batch_id=batch.id,
            started_offset_seconds=10,
        )
        own_a = await _seed_module(
            db_session,
            module_json={"cards": [{"title": {"bn": "a1"}, "body": {"bn": "x"}}]},
        )
        own_a.source_document_ids = [run_a.source_document_id]
        fused = await _seed_module(
            db_session,
            module_json={
                "cards": [
                    {"title": {"bn": "f1"}, "body": {"bn": "y"}},
                    {"title": {"bn": "f2"}, "body": {"bn": "z"}},
                ]
            },
        )
        fused.source_document_ids = [run_a.source_document_id, run_b.source_document_id]
        await db_session.commit()

        await self._add_card_draft_step(db_session, run_a, module_id=str(own_a.id))
        await self._freeze_counts(db_session, run_a)
        await self._freeze_counts(db_session, run_b)

        list_before = await client.get(platform_path("/admin/ingestion-runs"))
        by_id = {row["id"]: row for row in list_before.json()["runs"]}
        assert by_id[str(run_a.id)]["generated_module_count"] == 1
        assert by_id[str(run_a.id)]["generated_card_count"] == 1
        assert by_id[str(run_b.id)]["generated_module_count"] == 0

        fusion_run = await self._seed_run(
            db_session,
            original_filename="fusion-anchor.pdf",
            source_document_id=run_a.source_document_id,
            ingest_batch_id=batch.id,
            started_offset_seconds=20,
            error_jsonb={
                "type": FUSION_RUN_TYPE,
                "source_document_ids": [
                    str(run_a.source_document_id),
                    str(run_b.source_document_id),
                ],
            },
        )
        await self._add_card_draft_step(db_session, fusion_run, module_id=str(fused.id))
        await IngestionRunGenerationCountsService(db_session).upsert_after_run_complete(fusion_run)
        await db_session.commit()

        list_after = await client.get(platform_path("/admin/ingestion-runs"))
        by_id = {row["id"]: row for row in list_after.json()["runs"]}
        # Latest-per-document list hides the older pipeline run for doc A.
        assert str(run_a.id) not in by_id
        assert str(fusion_run.id) in by_id
        assert by_id[str(run_b.id)]["generated_module_count"] == 1
        assert by_id[str(run_b.id)]["generated_card_count"] == 2

        detail_a = await client.get(platform_path(f"/admin/ingestion-runs/{run_a.id}"))
        assert detail_a.json()["generated_module_count"] == 2
        assert detail_a.json()["generated_card_count"] == 3

    async def test_list_and_detail_include_ingested_by_actor(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session, tenant_id=1)
        await db_session.commit()
        run = await self._seed_run(db_session, ingested_by=AM_ID, started_offset_seconds=0)
        await self._seed_run(db_session, ingested_by=888_888, started_offset_seconds=10)

        list_resp = await client.get(platform_path("/admin/ingestion-runs"))
        assert list_resp.status_code == 200
        by_id = {row["id"]: row for row in list_resp.json()["runs"]}
        assert by_id[str(run.id)]["ingested_by"] == {"id": AM_ID, "name": "Test Area Manager"}
        missing_user_row = next(row for row in list_resp.json()["runs"] if row["id"] != str(run.id))
        assert missing_user_row["ingested_by"] is None

        detail = await client.get(platform_path(f"/admin/ingestion-runs/{run.id}"))
        assert detail.status_code == 200
        assert detail.json()["ingested_by"] == {"id": AM_ID, "name": "Test Area Manager"}

    async def test_list_filters_by_ingested_by(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session, tenant_id=1)
        await db_session.commit()
        match = await self._seed_run(db_session, ingested_by=AM_ID, started_offset_seconds=0)
        await self._seed_run(db_session, ingested_by=PO_ID, started_offset_seconds=10)
        await self._seed_run(db_session, ingested_by=None, started_offset_seconds=20)

        resp = await client.get(platform_path(f"/admin/ingestion-runs?ingested_by={AM_ID}"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_runs"] == 1
        assert body["runs"][0]["id"] == str(match.id)
        assert body["runs"][0]["ingested_by"] == {"id": AM_ID, "name": "Test Area Manager"}

        multi = await client.get(platform_path(f"/admin/ingestion-runs?ingested_by={AM_ID},{PO_ID}"))
        assert multi.status_code == 200
        assert multi.json()["total_runs"] == 2

        invalid = await client.get(platform_path("/admin/ingestion-runs?ingested_by=not-an-id"))
        assert invalid.status_code == 422

    async def test_detail_404_for_unknown(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path(f"/admin/ingestion-runs/{uuid4()}"))
        assert resp.status_code == 404
