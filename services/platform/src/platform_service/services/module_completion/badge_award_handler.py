"""Award badges when a CHW newly completes a linked module version."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.repositories.badge_repository import BadgeRepository
from platform_service.db.repositories.chw_badge_repository import CHWBadgeRepository
from platform_service.services.module_completion.quiz_coverage import (
    is_module_quiz_coverage_complete,
)

logger = logging.getLogger(__name__)


class BadgeAwardHandler:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._badges = BadgeRepository(session)
        self._awards = CHWBadgeRepository(session)

    async def try_award_for_completed_module(
        self,
        *,
        chw_id: int,
        tenant_id: int,
        module_id: UUID,
    ) -> None:
        """Evaluate active same-tenant badges linking ``module_id`` and award when complete."""
        if tenant_id is None:
            logger.info(
                "badge_award: skip chw_id=%s module_id=%s — missing tenant_id",
                chw_id,
                module_id,
            )
            return

        badge_ids = await self._badges.list_active_badge_ids_for_module(
            module_id=module_id,
            tenant_id=tenant_id,
        )
        if not badge_ids:
            logger.info(
                "badge_award: no active candidate badges chw_id=%s tenant_id=%s module_id=%s",
                chw_id,
                tenant_id,
                module_id,
            )
            return

        modules_by_badge = await self._badges.list_published_module_ids_for_badges(badge_ids)
        logger.info(
            "badge_award: evaluating candidates=%s chw_id=%s tenant_id=%s module_id=%s",
            len(badge_ids),
            chw_id,
            tenant_id,
            module_id,
        )

        for badge_id in badge_ids:
            linked_module_ids = modules_by_badge.get(badge_id) or []
            if not linked_module_ids:
                logger.info(
                    "badge_award: skip empty badge_id=%s chw_id=%s",
                    badge_id,
                    chw_id,
                )
                continue

            incomplete = False
            for linked_module_id in linked_module_ids:
                complete = await is_module_quiz_coverage_complete(
                    self._session,
                    chw_id=chw_id,
                    module_id=linked_module_id,
                )
                if not complete:
                    logger.info(
                        "badge_award: skip incomplete badge_id=%s chw_id=%s incomplete_module_id=%s",
                        badge_id,
                        chw_id,
                        linked_module_id,
                    )
                    incomplete = True
                    break
            if incomplete:
                continue

            inserted = await self._awards.try_insert_award(
                chw_id=chw_id,
                badge_id=badge_id,
                tenant_id=tenant_id,
            )
            if inserted:
                logger.info(
                    "badge_award: awarded badge_id=%s chw_id=%s tenant_id=%s",
                    badge_id,
                    chw_id,
                    tenant_id,
                )
            else:
                logger.info(
                    "badge_award: already awarded badge_id=%s chw_id=%s",
                    badge_id,
                    chw_id,
                )
