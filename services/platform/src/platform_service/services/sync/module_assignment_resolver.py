"""Resolve which module IDs are assigned to a user for device sync."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from platform_service.db.models.module import Module
from platform_service.db.models.module_assignment import ModuleAssignment
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.module_availability import is_training_module_family


def _assignment_filters(*, user_id: int, tenant_id: int) -> tuple[ColumnElement[bool], ...]:
    """Shared predicates for per-user assignment resolution."""
    return (
        ModuleAssignment.user_id == user_id,
        ModuleAssignment.tenant_id == tenant_id,
        is_training_module_family(),
    )


async def resolve_assigned_module_ids(
    session: AsyncSession,
    *,
    user_id: int,
    tenant_id: int,
) -> set[UUID]:
    """Return module IDs with a direct per-user assignment row for ``user_id``."""
    stmt = (
        select(ModuleAssignment.module_id)
        .join(Module, ModuleAssignment.module_id == Module.id)
        .join(ModuleFamily, Module.module_family_id == ModuleFamily.id)
        .where(*_assignment_filters(user_id=user_id, tenant_id=tenant_id))
    )
    return set((await session.execute(stmt)).scalars().all())


async def resolve_assigned_modules(
    session: AsyncSession,
    *,
    user_id: int,
    tenant_id: int,
) -> dict[UUID, datetime]:
    """Return module_id -> latest assigned_at for modules assigned to ``user_id``."""
    stmt = (
        select(
            ModuleAssignment.module_id,
            func.max(ModuleAssignment.assigned_at),
        )
        .join(Module, ModuleAssignment.module_id == Module.id)
        .join(ModuleFamily, Module.module_family_id == ModuleFamily.id)
        .where(*_assignment_filters(user_id=user_id, tenant_id=tenant_id))
        .group_by(ModuleAssignment.module_id)
    )
    res = await session.execute(stmt)
    return {row[0]: row[1] for row in res.all()}
