"""Service for module assignments business logic and orchestration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from mc_contracts.assignments import (
    AssignmentCreateRequest,
    AssignmentUpdateRequest,
    AssignmentUpdateResponse,
    ModuleAssignmentUsersResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.module import Module
from platform_service.db.models.module_assignment import ModuleAssignment
from platform_service.db.repositories.module_assignment_repository import ModuleAssignmentRepository
from platform_service.db.repositories.module_family_repository import ModuleFamilyRepository
from platform_service.services.assignment_assignees import (
    AssignmentValidationError,
    resolve_assignee_user_ids,
)
from platform_service.services.hierarchy_user_mapping import hierarchy_users_by_id


class ModuleNotFoundError(Exception):
    """Raised when the target module is not found."""

    pass


class ModuleAssignmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ModuleAssignmentRepository(session)

    async def create_assignments(
        self,
        body: AssignmentCreateRequest,
        assigned_by: int,
        *,
        tenant_id: int = DEFAULT_TENANT_ID,
        commit: bool = True,
    ) -> dict[str, Any]:
        """Create module assignments for resolved PO/SK assignees.

        When ``commit`` is False the caller owns the transaction (e.g. demand
        assign + attribution audit in one commit).
        """
        module = await self._session.get(Module, body.module_id)
        if not module:
            raise ModuleNotFoundError(f"Module with ID {body.module_id} not found")

        family_repo = ModuleFamilyRepository(self._session)
        if not await family_repo.is_assignable(module.module_family_id):
            raise AssignmentValidationError(
                "Module cannot be assigned: it is unpublished, deactivated, or chatbot-FAQ-only"
            )

        users_by_id = await hierarchy_users_by_id(self._session, tenant_id=tenant_id)
        assignee_ids = resolve_assignee_user_ids(
            user_ids=body.user_ids,
            upazilas=body.upazilas,
            users_by_id=users_by_id,
            expand_po_assignees=body.expand_po_assignees,
        )

        created_ids = []
        for user_id in sorted(assignee_ids):
            existing = await self._repo.find_user_assignment(body.module_id, user_id)
            if existing:
                created_ids.append(existing.id)
                continue

            new_assignment = ModuleAssignment(
                module_id=body.module_id,
                user_id=user_id,
                tenant_id=tenant_id,
                assigned_by=assigned_by,
            )
            self._repo.add_assignment(new_assignment)
            await self._session.flush()
            created_ids.append(new_assignment.id)

        if commit:
            await self._session.commit()
        else:
            await self._session.flush()
        return {
            "assigned_count": len(created_ids),
            "assignment_ids": [str(x) for x in created_ids],
        }

    async def update_assignments(
        self,
        module_id: UUID,
        body: AssignmentUpdateRequest,
        assigned_by: int,
        *,
        tenant_id: int = DEFAULT_TENANT_ID,
        commit: bool = True,
    ) -> AssignmentUpdateResponse:
        """Replace module assignments with the resolved PO/SK assignee set."""
        module = await self._session.get(Module, module_id)
        if not module:
            raise ModuleNotFoundError(f"Module with ID {module_id} not found")
        if module.tenant_id is not None and module.tenant_id != tenant_id:
            raise ModuleNotFoundError(f"Module with ID {module_id} not found")

        users_by_id = await hierarchy_users_by_id(self._session, tenant_id=tenant_id)
        target_ids = resolve_assignee_user_ids(
            user_ids=body.user_ids,
            upazilas=body.upazilas,
            users_by_id=users_by_id,
            allow_empty=True,
            expand_po_assignees=body.expand_po_assignees,
        )

        current_ids = set(await self._repo.list_user_ids_for_module(module_id, tenant_id=tenant_id))
        to_add = target_ids - current_ids
        to_remove = current_ids - target_ids

        if to_add:
            family_repo = ModuleFamilyRepository(self._session)
            if not await family_repo.is_assignable(module.module_family_id):
                raise AssignmentValidationError(
                    "Module cannot be assigned: it is unpublished, deactivated, or chatbot-FAQ-only"
                )

        removed_count = await self._repo.delete_assignments_for_users(
            module_id,
            to_remove,
            tenant_id=tenant_id,
        )

        for user_id in sorted(to_add):
            new_assignment = ModuleAssignment(
                module_id=module_id,
                user_id=user_id,
                tenant_id=tenant_id,
                assigned_by=assigned_by,
            )
            self._repo.add_assignment(new_assignment)

        if commit:
            await self._session.commit()
        else:
            await self._session.flush()

        assignment_ids = await self._repo.list_assignment_ids_for_module(
            module_id,
            tenant_id=tenant_id,
        )
        return AssignmentUpdateResponse(
            added_count=len(to_add),
            removed_count=removed_count,
            assignment_ids=[str(assignment_id) for assignment_id in assignment_ids],
        )

    async def list_assigned_users(
        self,
        module_id: UUID,
        *,
        tenant_id: int = DEFAULT_TENANT_ID,
    ) -> ModuleAssignmentUsersResponse:
        """Return hierarchy user details for all assignees of a module."""
        module = await self._session.get(Module, module_id)
        if not module:
            raise ModuleNotFoundError(f"Module with ID {module_id} not found")
        if module.tenant_id is not None and module.tenant_id != tenant_id:
            raise ModuleNotFoundError(f"Module with ID {module_id} not found")

        assignee_ids = await self._repo.list_user_ids_for_module(module_id, tenant_id=tenant_id)
        users_by_id = await hierarchy_users_by_id(self._session, tenant_id=tenant_id)
        users = sorted(
            (users_by_id[user_id] for user_id in assignee_ids if user_id in users_by_id),
            key=lambda user: user.name.casefold(),
        )
        return ModuleAssignmentUsersResponse(module_id=module_id, users=users)
