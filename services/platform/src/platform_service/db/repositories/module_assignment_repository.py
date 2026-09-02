"""Repository for ModuleAssignment database operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.module import Module
from platform_service.db.models.module_assignment import ModuleAssignment
from platform_service.db.module_availability import is_training_module_family


class ModuleAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_user_assignment(self, module_id: UUID, user_id: int) -> ModuleAssignment | None:
        """Find an existing user assignment."""
        stmt = select(ModuleAssignment).where(
            ModuleAssignment.module_id == module_id,
            ModuleAssignment.user_id == user_id,
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def list_user_ids_for_module(self, module_id: UUID, *, tenant_id: int) -> list[int]:
        """Return assignee user ids for a module within a tenant."""
        stmt = (
            select(ModuleAssignment.user_id)
            .where(
                ModuleAssignment.module_id == module_id,
                ModuleAssignment.tenant_id == tenant_id,
            )
            .order_by(ModuleAssignment.user_id)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    def add_assignment(self, assignment: ModuleAssignment) -> None:
        """Add a new assignment to the session."""
        self._session.add(assignment)

    async def delete_assignments_for_users(
        self,
        module_id: UUID,
        user_ids: set[int],
        *,
        tenant_id: int,
    ) -> int:
        """Delete assignment rows for the given users on a module within a tenant."""
        if not user_ids:
            return 0
        stmt = delete(ModuleAssignment).where(
            ModuleAssignment.module_id == module_id,
            ModuleAssignment.tenant_id == tenant_id,
            ModuleAssignment.user_id.in_(user_ids),
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount)

    async def list_assignment_ids_for_module(
        self,
        module_id: UUID,
        *,
        tenant_id: int,
    ) -> list[UUID]:
        """Return assignment row ids for a module within a tenant."""
        stmt = (
            select(ModuleAssignment.id)
            .where(
                ModuleAssignment.module_id == module_id,
                ModuleAssignment.tenant_id == tenant_id,
            )
            .order_by(ModuleAssignment.id)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_assignments_for_families_and_chws(
        self,
        *,
        family_ids: list[UUID],
        chw_ids: list[int],
        tenant_id: int,
    ) -> list[tuple[UUID, int]]:
        """Return (module_family_id, user_id) pairs for assigned CHWs across given families."""
        if not family_ids or not chw_ids:
            return []

        stmt = (
            select(Module.module_family_id, ModuleAssignment.user_id)
            .join(Module, ModuleAssignment.module_id == Module.id)
            .where(
                Module.module_family_id.in_(family_ids),
                ModuleAssignment.user_id.in_(chw_ids),
                ModuleAssignment.tenant_id == tenant_id,
            )
        )
        return list((await self._session.execute(stmt)).tuples().all())

    async def list_module_ids_assigned_in_range_for_chws(
        self,
        *,
        chw_ids: list[int],
        tenant_id: int,
        from_ts: datetime,
        to_ts: datetime,
    ) -> dict[int, set[UUID]]:
        """Return training module IDs with ``assigned_at`` in ``[from_ts, to_ts]`` per CHW.

        Only surviving ``module_assignment`` rows are considered (unassign deletes history).
        FAQ-only modules are excluded via the shared training-module filter.
        """
        if not chw_ids:
            return {}

        stmt = (
            select(ModuleAssignment.user_id, ModuleAssignment.module_id)
            .join(Module, ModuleAssignment.module_id == Module.id)
            .where(
                ModuleAssignment.user_id.in_(chw_ids),
                ModuleAssignment.tenant_id == tenant_id,
                ModuleAssignment.assigned_at >= from_ts,
                ModuleAssignment.assigned_at <= to_ts,
                is_training_module_family(),
            )
        )
        out: dict[int, set[UUID]] = {}
        for user_id, module_id in (await self._session.execute(stmt)).all():
            out.setdefault(int(user_id), set()).add(module_id)
        return out
