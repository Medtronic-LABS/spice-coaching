"""Build badges sync payload for device sync endpoint."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from mc_contracts.sync import AvailableBadgePayload, BadgesSyncBundle, EarnedBadgePayload
from mc_foundation.objectstore import ObjectStore
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import Settings, get_settings
from platform_service.db.repositories.badge_repository import BadgeRepository
from platform_service.db.repositories.chw_badge_repository import CHWBadgeRepository
from platform_service.services.source_thumbnail_service import presign_thumbnail

logger = logging.getLogger(__name__)


class BadgesBundleBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._badge_repo = BadgeRepository(session)
        self._chw_badge_repo = CHWBadgeRepository(session)

    async def build(
        self,
        *,
        user_id: int,
        tenant_id: int,
        storage: ObjectStore,
        settings: Settings | None = None,
    ) -> BadgesSyncBundle:
        settings = settings or get_settings()

        active_badges = await self._badge_repo.list_active_for_tenant(tenant_id)
        earned_tuples = await self._chw_badge_repo.list_earned_for_chw(
            chw_id=user_id,
            tenant_id=tenant_id,
        )

        all_badge_ids = list({badge.id for badge in active_badges} | {badge.id for _, badge in earned_tuples})
        module_ids_map = await self._badge_repo.list_module_ids_for_badges(all_badge_ids)

        available_badges: list[AvailableBadgePayload] = []
        for badge in active_badges:
            thumb = await presign_thumbnail(
                storage,
                thumbnail_storage_path=badge.image_storage_path,
                settings=settings,
            )
            available_badges.append(
                AvailableBadgePayload(
                    id=badge.id,
                    name=badge.name,
                    domain=badge.domain,
                    image_storage_path=badge.image_storage_path,
                    image_presigned_url=thumb[0] if thumb else None,
                    image_presigned_expires_seconds=thumb[1] if thumb else None,
                    sequence=badge.sequence,
                    module_ids=module_ids_map.get(badge.id, []),
                )
            )

        earned_badges: list[EarnedBadgePayload] = []
        for chw_badge, badge in earned_tuples:
            thumb = await presign_thumbnail(
                storage,
                thumbnail_storage_path=badge.image_storage_path,
                settings=settings,
            )
            earned_badges.append(
                EarnedBadgePayload(
                    id=badge.id,
                    name=badge.name,
                    domain=badge.domain,
                    image_storage_path=badge.image_storage_path,
                    image_presigned_url=thumb[0] if thumb else None,
                    image_presigned_expires_seconds=thumb[1] if thumb else None,
                    sequence=badge.sequence,
                    module_ids=module_ids_map.get(badge.id, []),
                    earned_at=chw_badge.earned_at,
                )
            )

        logger.info(
            "sync_badges user_id=%s tenant_id=%s available=%s earned=%s",
            user_id,
            tenant_id,
            len(available_badges),
            len(earned_badges),
        )

        return BadgesSyncBundle(
            available_badges=available_badges,
            earned_badges=earned_badges,
            server_time_utc=datetime.now(UTC).isoformat(),
        )
