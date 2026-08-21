"""Persistence for CHW earned badges — one row per (chw_id, badge_id)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.badge import Badge
from platform_service.db.models.chw_badge import CHWBadge


class CHWBadgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_insert_award(
        self,
        *,
        chw_id: int,
        badge_id: uuid.UUID,
        tenant_id: int,
        earned_at: datetime | None = None,
    ) -> bool:
        """Insert an award once; duplicate (chw_id, badge_id) is a no-op.

        Returns True when a new row was inserted.
        """
        when = earned_at if earned_at is not None else datetime.now(UTC)
        stmt = (
            pg_insert(CHWBadge)
            .values(
                chw_id=chw_id,
                badge_id=badge_id,
                tenant_id=tenant_id,
                earned_at=when,
            )
            .on_conflict_do_nothing(index_elements=[CHWBadge.chw_id, CHWBadge.badge_id])
            .returning(CHWBadge.badge_id)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def list_earned_for_chw(
        self,
        *,
        chw_id: int,
        tenant_id: int,
    ) -> list[tuple[CHWBadge, Badge]]:
        """List earned badges for a CHW in a tenant (including soft-deleted catalog badges)."""
        stmt = (
            select(CHWBadge, Badge)
            .join(Badge, CHWBadge.badge_id == Badge.id)
            .where(
                CHWBadge.chw_id == chw_id,
                CHWBadge.tenant_id == tenant_id,
            )
            .order_by(CHWBadge.earned_at.desc())
        )
        res = await self._session.execute(stmt)
        return list(res.tuples().all())
