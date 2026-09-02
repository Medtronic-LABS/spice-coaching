"""Shared card coverage checks for a CHW × module version."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.chw_module_card_progress import CHWModuleCardProgress
from platform_service.db.models.module_card import ModuleCard


async def card_coverage_count(
    session: AsyncSession,
    *,
    chw_id: int,
    module_id: UUID,
) -> tuple[list[UUID], int]:
    """Return (card_ids for module version, distinct progress rows covering them)."""
    card_ids = list(
        (
            await session.execute(
                select(ModuleCard.id)
                .where(ModuleCard.module_id == module_id)
                .order_by(ModuleCard.card_order.asc(), ModuleCard.id.asc())
            )
        )
        .scalars()
        .all()
    )
    if not card_ids:
        return card_ids, 0

    covered_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(CHWModuleCardProgress)
                .where(
                    CHWModuleCardProgress.chw_id == chw_id,
                    CHWModuleCardProgress.module_id == module_id,
                    CHWModuleCardProgress.card_id.in_(card_ids),
                )
            )
        ).scalar_one()
    )
    return card_ids, covered_count


async def is_module_card_coverage_complete(
    session: AsyncSession,
    *,
    chw_id: int,
    module_id: UUID,
) -> bool:
    """True when the module has ≥1 cards and the CHW has viewed all of them."""
    card_ids, covered_count = await card_coverage_count(session, chw_id=chw_id, module_id=module_id)
    return bool(card_ids) and covered_count >= len(card_ids)
