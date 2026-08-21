"""Dashboard module demand summary — composes usage + creation suggestions."""

from __future__ import annotations

import asyncio
from datetime import date

from mc_contracts.dashboard import ModuleDemandSummaryResponse
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.clickhouse.client import ClickHouseClient
from platform_service.db.repositories.module_creation_suggestion_repository import (
    ModuleCreationSuggestionRepository,
)
from platform_service.services.dashboard_analytics_service import DashboardAnalyticsService
from platform_service.services.module_creation_suggestion_classifier import (
    SUGGESTION_KIND_MATCHED_DRAFT,
)
from platform_service.services.module_creation_suggestion_service import (
    ModuleCreationSuggestionService,
)
from platform_service.services.prompts.module_demand_summary_text import (
    build_module_demand_summary,
)

DEFAULT_TOP_LIMIT = 10
_USAGE_PAGE_LIMIT = 1


class ModuleDemandSummaryService:
    def __init__(
        self,
        ch_client: ClickHouseClient,
        session: AsyncSession,
    ) -> None:
        self._analytics = DashboardAnalyticsService(ch_client, session)
        self._session = session
        self._suggestion_repo = ModuleCreationSuggestionRepository(session)

    async def get_summary(
        self,
        *,
        tenant_id: int | None,
        from_date: date,
        to_date: date,
        chw_ids: frozenset[int] | None,
        top_limit: int = DEFAULT_TOP_LIMIT,
    ) -> ModuleDemandSummaryResponse:
        """Compose the structured demand summary from full-window category volumes.

        ``top_limit`` is accepted for API compatibility and is not used for scoring.
        """
        _ = top_limit
        usage_task = self._analytics.get_digital_help_module_usage(
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            limit=_USAGE_PAGE_LIMIT,
            offset=0,
            chw_ids=chw_ids,
        )
        volumes_task = self._creation_volumes(
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            chw_ids=chw_ids,
        )
        usage, (publish_volume, create_volume) = await asyncio.gather(usage_task, volumes_task)
        return build_module_demand_summary(
            from_date=from_date,
            to_date=to_date,
            assign_volume=usage.total_digital_help + usage.total_module_requested,
            publish_volume=publish_volume,
            create_volume=create_volume,
        )

    async def _creation_volumes(
        self,
        *,
        tenant_id: int | None,
        from_date: date,
        to_date: date,
        chw_ids: frozenset[int] | None,
    ) -> tuple[int, int]:
        rows = await self._suggestion_repo.list_all_in_range(
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            visible_chw_ids=chw_ids,
        )
        publish_volume = 0
        create_volume = 0
        for row in rows:
            item = ModuleCreationSuggestionService._to_list_item(
                row,
                visible_chw_ids=chw_ids,
            )
            if item.evidence_count <= 0:
                continue
            volume = item.request_count + item.question_count
            if item.suggestion_kind == SUGGESTION_KIND_MATCHED_DRAFT:
                publish_volume += volume
            else:
                create_volume += volume
        return publish_volume, create_volume
