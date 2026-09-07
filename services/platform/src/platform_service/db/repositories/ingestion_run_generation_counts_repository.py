"""Persistence for frozen ingestion_run generation counts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.ingestion_run import IngestionRun, IngestionRunGenerationCounts
from platform_service.services.run_state.constants import now_utc


class IngestionRunGenerationCountsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        ingestion_run_id: UUID,
        source_document_id: UUID,
        generated_module_count: int,
        generated_card_count: int,
        generated_quiz_count: int,
        computed_at: datetime | None = None,
    ) -> IngestionRunGenerationCounts:
        when = computed_at or now_utc()
        stmt = (
            insert(IngestionRunGenerationCounts)
            .values(
                ingestion_run_id=ingestion_run_id,
                source_document_id=source_document_id,
                generated_module_count=generated_module_count,
                generated_card_count=generated_card_count,
                generated_quiz_count=generated_quiz_count,
                computed_at=when,
            )
            .on_conflict_do_update(
                index_elements=[
                    IngestionRunGenerationCounts.ingestion_run_id,
                    IngestionRunGenerationCounts.source_document_id,
                ],
                set_={
                    "generated_module_count": generated_module_count,
                    "generated_card_count": generated_card_count,
                    "generated_quiz_count": generated_quiz_count,
                    "computed_at": when,
                },
            )
            .returning(IngestionRunGenerationCounts)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        await self._session.flush()
        return row

    async def get_for_runs(
        self,
        run_ids: list[UUID],
    ) -> dict[UUID, IngestionRunGenerationCounts]:
        if not run_ids:
            return {}
        result = await self._session.execute(
            select(IngestionRunGenerationCounts).where(
                IngestionRunGenerationCounts.ingestion_run_id.in_(run_ids)
            )
        )
        return {row.ingestion_run_id: row for row in result.scalars().all()}

    async def list_pipeline_runs_for_batch_sources(
        self,
        batch_id: UUID,
        source_document_ids: list[UUID],
    ) -> list[IngestionRun]:
        """Pipeline runs in ``batch_id`` for the given source documents."""
        if not source_document_ids:
            return []
        result = await self._session.execute(
            select(IngestionRun).where(
                IngestionRun.ingest_batch_id == batch_id,
                IngestionRun.source_document_id.in_(source_document_ids),
            )
        )
        return list(result.scalars().all())
