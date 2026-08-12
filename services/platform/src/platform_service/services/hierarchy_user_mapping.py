"""Map hierarchy users into assignment UserResponse DTOs."""

from __future__ import annotations

from mc_contracts.assignments import AssignmentUpazilaRef, UserResponse
from mc_contracts.enums import HierarchyRole
from mc_contracts.hierarchy import HierarchyUserResponse
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.services.hierarchy_service import HierarchyService


async def hierarchy_users_by_id(
    session: AsyncSession,
    *,
    tenant_id: int,
) -> dict[int, UserResponse]:
    """Load all tenant hierarchy users keyed by id for assignment enrichment."""
    hierarchy = HierarchyService(session)
    users = await hierarchy.list_all_users(tenant_id=tenant_id)
    district_names = await hierarchy.district_names_by_ids(
        {u.district_id for u in users},
        tenant_id=tenant_id,
    )
    return {
        u.id: hierarchy_user_to_assignment_user(
            u,
            district_name=district_names.get(u.district_id, ""),
        )
        for u in users
    }


def hierarchy_user_to_assignment_user(
    user: HierarchyUserResponse,
    *,
    district_name: str,
) -> UserResponse:
    role = user.role if isinstance(user.role, HierarchyRole) else HierarchyRole(str(user.role))
    return UserResponse(
        id=user.id,
        name=user.name,
        role=role,
        parent_id=user.parent_id,
        district_id=user.district_id,
        district=district_name,
        upazilas=[AssignmentUpazilaRef(id=u.id, name=u.name) for u in user.upazilas],
    )
