"""Dashboard module demand text summary — composes usage + creation suggestions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from mc_contracts.dashboard import ModuleCreationSuggestionListItem, ModuleDemandSummaryResponse
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.clickhouse.client import ClickHouseClient
from platform_service.db.repositories.module_creation_suggestion_repository import (
    ModuleCreationSuggestionRepository,
)
from platform_service.services.dashboard_analytics_service import DashboardAnalyticsService
from platform_service.services.module_creation_suggestion_classifier import (
    SUGGESTION_KIND_MATCHED_DRAFT,
    SUGGESTION_KIND_PROPOSED_TOPIC,
)
from platform_service.services.module_creation_suggestion_service import (
    ModuleCreationSuggestionService,
)
from platform_service.services.prompts.module_demand_summary_text import (
    AggregatedCreationDemand,
    build_module_demand_text_summary,
)

DEFAULT_TOP_LIMIT = 10
MAX_TOP_LIMIT = 50


@dataclass
class _AggregatedCreationAccumulator:
    suggestion_kind: str
    display_title: str
    matched_module_id: UUID | None
    question_count: int = 0
    request_count: int = 0
    evidence_count: int = 0


class ModuleDemandSummaryService:
    def __init__(
        self,
        ch_client: ClickHouseClient,
        session: AsyncSession,
    ) -> None:
        self._analytics = DashboardAnalyticsService(ch_client, session)
        self._session = session
        self._suggestion_repo = ModuleCreationSuggestionRepository(session)

    async def get_text_summary(
        self,
        *,
        tenant_id: int | None,
        from_date: date,
        to_date: date,
        chw_ids: frozenset[int] | None,
        top_limit: int = DEFAULT_TOP_LIMIT,
    ) -> ModuleDemandSummaryResponse:
        limit = min(max(1, top_limit), MAX_TOP_LIMIT)
        usage_task = self._analytics.get_digital_help_module_usage(
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=0,
            chw_ids=chw_ids,
        )
        suggestions_task = self._fetch_aggregated_creation_demand(
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            chw_ids=chw_ids,
            top_limit=limit,
        )
        usage, creation_demand = await asyncio.gather(usage_task, suggestions_task)
        summary = build_module_demand_text_summary(
            from_date=from_date,
            to_date=to_date,
            usage_modules=list(usage.modules),
            creation_demand=creation_demand,
        )
        return ModuleDemandSummaryResponse(
            from_date=from_date,
            to_date=to_date,
            summary=summary,
        )

    async def _fetch_aggregated_creation_demand(
        self,
        *,
        tenant_id: int | None,
        from_date: date,
        to_date: date,
        chw_ids: frozenset[int] | None,
        top_limit: int,
    ) -> list[AggregatedCreationDemand]:
        rows = await self._suggestion_repo.list_all_in_range(
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            visible_chw_ids=chw_ids,
        )
        grouped: dict[tuple[str, UUID | str], _AggregatedCreationAccumulator] = {}
        for row in rows:
            item = ModuleCreationSuggestionService._to_list_item(
                row,
                visible_chw_ids=chw_ids,
            )
            if item.evidence_count <= 0:
                continue
            key = self._aggregation_key(item)
            acc = grouped.get(key)
            if acc is None:
                acc = _AggregatedCreationAccumulator(
                    suggestion_kind=item.suggestion_kind,
                    display_title=item.display_title,
                    matched_module_id=item.matched_module_id,
                )
                grouped[key] = acc
            acc.question_count += item.question_count
            acc.request_count += item.request_count
            acc.evidence_count += item.evidence_count

        ranked = sorted(
            grouped.values(),
            key=lambda acc: acc.evidence_count,
            reverse=True,
        )
        return [
            AggregatedCreationDemand(
                suggestion_kind=acc.suggestion_kind,
                display_title=acc.display_title,
                matched_module_id=acc.matched_module_id,
                question_count=acc.question_count,
                request_count=acc.request_count,
                evidence_count=acc.evidence_count,
            )
            for acc in ranked[:top_limit]
        ]

    @staticmethod
    def _aggregation_key(item: ModuleCreationSuggestionListItem) -> tuple[str, UUID | str]:
        if item.suggestion_kind == SUGGESTION_KIND_MATCHED_DRAFT and item.matched_module_id is not None:
            return (item.suggestion_kind, item.matched_module_id)
        if item.suggestion_kind == SUGGESTION_KIND_PROPOSED_TOPIC:
            topic = (item.proposed_topic or item.display_title or "").strip().casefold()
            return (item.suggestion_kind, topic)
        return (item.suggestion_kind, item.display_title.strip().casefold())
