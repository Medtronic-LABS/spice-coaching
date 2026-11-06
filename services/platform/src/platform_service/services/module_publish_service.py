"""Admin module publish service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.repositories.module_lifecycle_repository import (
    ModuleLifecycleRepository,
    ModuleLifecycleState,
)
from platform_service.services.attribution_audit import record_attribution_event
from platform_service.services.module_assign_to_all_service import ModuleAssignToAllService
from platform_service.services.module_publish_enrichment import enrich_module_for_publish


class ModulePublishService:
    """Publish a module version and record attribution auditing."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._lifecycle_repo = ModuleLifecycleRepository(session)

    async def publish(
        self,
        module_id: UUID,
        *,
        actor_id: UUID | None = None,
        published_by_user_id: int | None = None,
        reason: str | None = None,
        assign_to_all: bool | None = None,
    ) -> ModuleLifecycleState:
        """Publish ``module_id``; a non-None ``assign_to_all`` is applied to it and its videos."""
        await enrich_module_for_publish(self._session, module_id)
        state = await self._lifecycle_repo.publish(
            module_id,
            actor_id=actor_id,
            published_by_user_id=published_by_user_id,
            reason=reason,
        )
        if assign_to_all is not None:
            await ModuleAssignToAllService(self._session).set_for_module(
                module_id,
                assign_to_all=assign_to_all,
                updated_by=published_by_user_id,
            )
        await record_attribution_event(
            self._session,
            event_type="module_published",
            actor=str(actor_id) if actor_id else "admin",
            module_id=module_id,
            payload={"module_family_id": str(state.module_family_id), "reason": reason},
        )
        return state
