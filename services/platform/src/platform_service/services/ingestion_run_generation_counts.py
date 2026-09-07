"""Freeze and refresh per-run module/card/quiz generation counts."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.ingestion_run import IngestionRun, IngestionRunStep
from platform_service.db.models.module import Module
from platform_service.db.repositories.ingestion_run_generation_counts_repository import (
    IngestionRunGenerationCountsRepository,
)
from platform_service.services.module_presenter import get_card_counts, get_quiz_counts
from platform_service.services.run_state.constants import STAGE_CARD_DRAFT

logger = logging.getLogger(__name__)


def _uuid_from_step_summary(step: IngestionRunStep, key: str) -> UUID | None:
    summary = step.output_summary_jsonb or {}
    raw = summary.get(key)
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def primary_module_ids_from_card_draft_steps(
    steps: list[IngestionRunStep],
) -> list[UUID]:
    """Distinct primary ``module_id``s from card_draft steps; exclude secondaries."""
    seen: set[UUID] = set()
    secondary_ids: set[UUID] = set()
    ordered: list[UUID] = []
    for step in steps:
        if step.stage != STAGE_CARD_DRAFT:
            continue
        secondary_id = _uuid_from_step_summary(step, "secondary_module_id")
        if secondary_id is not None:
            secondary_ids.add(secondary_id)
        module_id = _uuid_from_step_summary(step, "module_id")
        if module_id is None or module_id in seen:
            continue
        seen.add(module_id)
        ordered.append(module_id)
    return [mid for mid in ordered if mid not in secondary_ids]


class IngestionRunGenerationCountsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = IngestionRunGenerationCountsRepository(session)

    async def _card_draft_steps_for_runs(
        self,
        run_ids: list[UUID],
    ) -> dict[UUID, list[IngestionRunStep]]:
        if not run_ids:
            return {}
        result = await self._session.execute(
            select(IngestionRunStep).where(
                IngestionRunStep.ingestion_run_id.in_(run_ids),
                IngestionRunStep.stage == STAGE_CARD_DRAFT,
            )
        )
        by_run: dict[UUID, list[IngestionRunStep]] = {rid: [] for rid in run_ids}
        for step in result.scalars().all():
            by_run.setdefault(step.ingestion_run_id, []).append(step)
        return by_run

    async def _shared_batch_module_ids(
        self,
        *,
        run: IngestionRun,
        own_module_ids: set[UUID],
    ) -> list[UUID]:
        """Primary modules from sibling batch runs that list this source document."""
        if run.ingest_batch_id is None:
            return []
        sibling_result = await self._session.execute(
            select(IngestionRun).where(
                IngestionRun.ingest_batch_id == run.ingest_batch_id,
                IngestionRun.id != run.id,
            )
        )
        siblings = list(sibling_result.scalars().all())
        if not siblings:
            return []
        steps_by_run = await self._card_draft_steps_for_runs([s.id for s in siblings])
        candidate_ids: list[UUID] = []
        seen: set[UUID] = set(own_module_ids)
        for sibling in siblings:
            for mid in primary_module_ids_from_card_draft_steps(steps_by_run.get(sibling.id, [])):
                if mid in seen:
                    continue
                seen.add(mid)
                candidate_ids.append(mid)
        if not candidate_ids:
            return []
        modules_result = await self._session.execute(select(Module).where(Module.id.in_(candidate_ids)))
        shared: list[UUID] = []
        for module in modules_result.scalars().all():
            if module.merge_primary_module_id is not None:
                continue
            source_ids = module.source_document_ids or []
            if run.source_document_id not in source_ids:
                continue
            shared.append(module.id)
        return shared

    async def compute_counts_for_run(
        self,
        run: IngestionRun,
    ) -> tuple[int, int, int]:
        steps_by_run = await self._card_draft_steps_for_runs([run.id])
        module_ids = primary_module_ids_from_card_draft_steps(steps_by_run.get(run.id, []))
        own_set = set(module_ids)
        shared = await self._shared_batch_module_ids(run=run, own_module_ids=own_set)
        module_ids = list(module_ids) + shared
        card_counts = await get_card_counts(self._session, module_ids)
        quiz_counts = await get_quiz_counts(self._session, module_ids)
        return (
            len(module_ids),
            sum(card_counts.get(mid, 0) for mid in module_ids),
            sum(quiz_counts.get(mid, 0) for mid in module_ids),
        )

    async def upsert_for_run(self, run_id: UUID) -> None:
        run = await self._session.get(IngestionRun, run_id)
        if run is None:
            return
        module_count, card_count, quiz_count = await self.compute_counts_for_run(run)
        await self._repo.upsert(
            ingestion_run_id=run.id,
            source_document_id=run.source_document_id,
            generated_module_count=module_count,
            generated_card_count=card_count,
            generated_quiz_count=quiz_count,
        )
        logger.info(
            "ingestion_run_generation_counts upserted run_id=%s source_document_id=%s "
            "modules=%d cards=%d quizzes=%d",
            run.id,
            run.source_document_id,
            module_count,
            card_count,
            quiz_count,
        )

    async def refresh_for_batch_source_documents(
        self,
        batch_id: UUID,
        source_document_ids: list[UUID],
    ) -> None:
        runs = await self._repo.list_pipeline_runs_for_batch_sources(batch_id, source_document_ids)
        for run in runs:
            await self.upsert_for_run(run.id)

    async def upsert_after_run_complete(self, run: IngestionRun) -> None:
        """Write this run's snapshot after it reaches a terminal status."""
        await self.upsert_for_run(run.id)
