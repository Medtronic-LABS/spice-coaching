"""Repository for ModuleAssignment database operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.module_assignment import ModuleAssignment


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
