"""Published module completions — Admin/AM rollout tracking for newly published modules."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from mc_contracts.dashboard import (
    PublishedModuleCompletionItem,
    PublishedModuleCompletionsResponse,
)
from mc_contracts.enums import HierarchyRole
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_identity import PublishedModuleCompletionsScope
from platform_service.db.repositories.module_assignment_repository import ModuleAssignmentRepository
from platform_service.db.repositories.module_completion_repository import ModuleCompletionRepository
from platform_service.db.repositories.module_repository import ModuleRepository
from platform_service.services.dashboard_hierarchy import (
    filter_users_by_chw_ids,
    org_user_index,
    sks_under_focus,
)


def _utc_range_bounds(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    from_ts = datetime.combine(from_date, time.min, tzinfo=UTC)
    to_ts = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC) - timedelta(microseconds=1)
    return from_ts, to_ts


class PublishedModuleCompletionsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_published_module_completions(
        self,
        *,
        scope: PublishedModuleCompletionsScope,
        from_date: date,
        to_date: date,
        limit: int,
        offset: int,
        tenant_id: int,
        geo_chw_ids: frozenset[int] | None = None,
    ) -> PublishedModuleCompletionsResponse:
        by_id = await org_user_index(self._session, tenant_id=tenant_id)
        if scope.unrestricted:
            visible_sks = sks_under_focus(by_id, None, None)
        else:
            if scope.viewer_id is None:
                visible_sks = []
            else:
                viewer = by_id.get(scope.viewer_id)
                if viewer is None or viewer.role != HierarchyRole.AREA_MANAGER.value:
                    visible_sks = []
                else:
                    visible_sks = sks_under_focus(by_id, viewer.id, viewer.role)

        visible_sks = filter_users_by_chw_ids(visible_sks, geo_chw_ids)

        total_descendant_sk_count = len(visible_sks)
        chw_ids = [sk.id for sk in visible_sks]
        from_ts, to_ts = _utc_range_bounds(from_date, to_date)

        module_repo = ModuleRepository(self._session)
        total_modules = await module_repo.count_modules(
            status="published",
            chatbot_faqs_only=False,
            published_from=from_ts,
            published_to=to_ts,
            tenant_id=tenant_id,
        )
        modules = await module_repo.list_modules(
            status="published",
            chatbot_faqs_only=False,
            published_from=from_ts,
            published_to=to_ts,
            tenant_id=tenant_id,
            sort_by="published_at",
            sort_dir="desc",
            limit=limit,
            offset=offset,
        )

        completed_by_family: dict[UUID, set[int]] = defaultdict(set)
        assigned_by_family: dict[UUID, set[int]] = defaultdict(set)

        if chw_ids and modules:
            visible_sk_ids = set(chw_ids)
            completions = await ModuleCompletionRepository(self._session).list_completed_in_range_for_chws(
                chw_ids=chw_ids,
                from_ts=from_ts,
                to_ts=to_ts,
            )
            for row in completions:
                if row.chw_id in visible_sk_ids:
                    completed_by_family[row.module_family_id].add(row.chw_id)

            module_family_ids = [m.module_family_id for m in modules]
            assignment_rows = await ModuleAssignmentRepository(
                self._session
            ).list_assignments_for_families_and_chws(
                family_ids=module_family_ids,
                chw_ids=chw_ids,
                tenant_id=tenant_id,
            )
            for family_id, user_id in assignment_rows:
                if user_id in visible_sk_ids:
                    assigned_by_family[family_id].add(user_id)

        items: list[PublishedModuleCompletionItem] = []
        for module in modules:
            published_at = module.published_at
            if published_at is None:
                # Date-range filter requires published_at; skip defensive edge cases.
                continue
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=UTC)
            family_id: UUID = module.module_family_id
            items.append(
                PublishedModuleCompletionItem(
                    module_id=module.id,
                    module_family_id=family_id,
                    title=module.title_localized if module.title_localized else None,
                    published_at=published_at,
                    completed_sk_count=len(completed_by_family.get(family_id, ())),
                    assigned_sk_count=len(assigned_by_family.get(family_id, ())),
                    total_descendant_sk_count=total_descendant_sk_count,
                )
            )

        return PublishedModuleCompletionsResponse(
            from_date=from_date,
            to_date=to_date,
            total_modules=total_modules,
            total_descendant_sk_count=total_descendant_sk_count,
            limit=limit,
            offset=offset,
            modules=items,
        )
