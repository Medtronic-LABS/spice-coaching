"""Persistence for daily module-creation suggestions and evidence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from platform_service.db.models.module_creation_suggestion import (
    ModuleCreationSuggestion,
    ModuleCreationSuggestionEvidence,
)


@dataclass(frozen=True)
class EvidenceRow:
    source: str
    text: str
    normalized_text: str
    occurrence_count: int
    last_seen_at: datetime | None
    sample_event_id: str | None
    sample_chw_id: int | None


@dataclass(frozen=True)
class SuggestionRow:
    suggestion_kind: str
    matched_module_id: uuid.UUID | None
    proposed_topic: str | None
    display_title: str
    rationale: str | None
    question_count: int
    request_count: int
    evidence_count: int
    rank: int
    evidence: list[EvidenceRow]


class ModuleCreationSuggestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _scope_filter(self, tenant_id: int):  # type: ignore[no-untyped-def]
        return ModuleCreationSuggestion.tenant_id == tenant_id

    def _visible_evidence_exists(self, visible_chw_ids: frozenset[int]):  # type: ignore[no-untyped-def]
        return exists().where(
            ModuleCreationSuggestionEvidence.suggestion_id == ModuleCreationSuggestion.id,
            ModuleCreationSuggestionEvidence.sample_chw_id.in_(list(visible_chw_ids)),
        )

    async def replace_for_day(
        self,
        *,
        tenant_id: int,
        suggestion_date: date,
        rows: list[SuggestionRow],
        computed_at: datetime,
    ) -> list[ModuleCreationSuggestion]:
        """Replace all suggestions for a tenant scope + UTC day."""
        await self._session.execute(
            delete(ModuleCreationSuggestion).where(
                self._scope_filter(tenant_id),
                ModuleCreationSuggestion.suggestion_date == suggestion_date,
            )
        )
        now = datetime.now(UTC)
        created: list[ModuleCreationSuggestion] = []
        for row in rows:
            suggestion = ModuleCreationSuggestion(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                suggestion_date=suggestion_date,
                suggestion_kind=row.suggestion_kind,
                matched_module_id=row.matched_module_id,
                proposed_topic=row.proposed_topic,
                display_title=row.display_title,
                rationale=row.rationale,
                question_count=row.question_count,
                request_count=row.request_count,
                evidence_count=row.evidence_count,
                rank=row.rank,
                computed_at=computed_at,
                created_at=now,
                updated_at=now,
            )
            for ev in row.evidence:
                suggestion.evidence.append(
                    ModuleCreationSuggestionEvidence(
                        id=uuid.uuid4(),
                        suggestion_id=suggestion.id,
                        source=ev.source,
                        text=ev.text,
                        normalized_text=ev.normalized_text,
                        occurrence_count=ev.occurrence_count,
                        last_seen_at=ev.last_seen_at,
                        sample_event_id=ev.sample_event_id,
                        sample_chw_id=ev.sample_chw_id,
                    )
                )
            self._session.add(suggestion)
            created.append(suggestion)
        await self._session.flush()
        return created

    async def list_in_range(
        self,
        *,
        tenant_id: int | None,
        from_date: date,
        to_date: date,
        limit: int,
        offset: int,
        visible_chw_ids: frozenset[int] | None = None,
    ) -> tuple[list[ModuleCreationSuggestion], int]:
        filters = [
            ModuleCreationSuggestion.suggestion_date >= from_date,
            ModuleCreationSuggestion.suggestion_date <= to_date,
        ]
        if tenant_id is not None:
            filters.append(self._scope_filter(tenant_id))
        if visible_chw_ids is not None:
            if len(visible_chw_ids) == 0:
                return [], 0
            filters.append(self._visible_evidence_exists(visible_chw_ids))

        count_stmt = select(func.count()).select_from(ModuleCreationSuggestion).where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())
        stmt = (
            select(ModuleCreationSuggestion)
            .where(*filters)
            .order_by(
                ModuleCreationSuggestion.suggestion_date.desc(),
                ModuleCreationSuggestion.rank.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        if visible_chw_ids is not None:
            stmt = stmt.options(selectinload(ModuleCreationSuggestion.evidence))
        result = await self._session.execute(stmt)
        rows = list(
            result.scalars().unique().all() if visible_chw_ids is not None else result.scalars().all()
        )
        return rows, total

    async def list_all_in_range(
        self,
        *,
        tenant_id: int | None,
        from_date: date,
        to_date: date,
        visible_chw_ids: frozenset[int] | None = None,
    ) -> list[ModuleCreationSuggestion]:
        """Return all suggestions in range (no pagination), with evidence loaded."""
        filters = [
            ModuleCreationSuggestion.suggestion_date >= from_date,
            ModuleCreationSuggestion.suggestion_date <= to_date,
        ]
        if tenant_id is not None:
            filters.append(self._scope_filter(tenant_id))
        if visible_chw_ids is not None:
            if len(visible_chw_ids) == 0:
                return []
            filters.append(self._visible_evidence_exists(visible_chw_ids))

        stmt = (
            select(ModuleCreationSuggestion)
            .where(*filters)
            .order_by(
                ModuleCreationSuggestion.suggestion_date.desc(),
                ModuleCreationSuggestion.rank.asc(),
            )
            .options(selectinload(ModuleCreationSuggestion.evidence))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_detail(
        self,
        *,
        suggestion_id: uuid.UUID,
        tenant_id: int | None,
        visible_chw_ids: frozenset[int] | None = None,
    ) -> ModuleCreationSuggestion | None:
        filters = [ModuleCreationSuggestion.id == suggestion_id]
        if tenant_id is not None:
            filters.append(self._scope_filter(tenant_id))
        if visible_chw_ids is not None:
            if len(visible_chw_ids) == 0:
                return None
            filters.append(self._visible_evidence_exists(visible_chw_ids))
        stmt = (
            select(ModuleCreationSuggestion)
            .where(*filters)
            .options(selectinload(ModuleCreationSuggestion.evidence))
        )
        return (await self._session.execute(stmt)).scalars().unique().first()
