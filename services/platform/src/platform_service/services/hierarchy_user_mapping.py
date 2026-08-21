"""Map hierarchy users into assignment UserResponse DTOs."""

from __future__ import annotations

from mc_contracts.assignments import AssignmentUpazilaRef, UserResponse
from mc_contracts.enums import HierarchyRole
from mc_contracts.hierarchy import HierarchyUserResponse
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.services.hierarchy_geo import non_null_district_ids
from platform_service.services.hierarchy_service import HierarchyService


async def hierarchy_users_by_id(
    session: AsyncSession,
    *,
    tenant_id: int,
) -> dict[int, UserResponse]:
    """Load all tenant hierarchy users keyed by id for assignment enrichment."""
    hierarchy = HierarchyService(session)
    users = await hierarchy.list_all_users(tenant_id=tenant_id)
    district_ids = non_null_district_ids(users)
    district_names = await hierarchy.district_names_by_ids(
        district_ids,
        tenant_id=tenant_id,
    )
    districts = await hierarchy.districts_by_ids(
        district_ids,
        tenant_id=tenant_id,
    )
    division_ids = {d.division_id for d in districts.values() if d.division_id is not None}
    division_names = await hierarchy.division_names_by_ids(division_ids, tenant_id=tenant_id)
    return {
        u.id: hierarchy_user_to_assignment_user(
            u,
            district_name=district_names.get(u.district_id) if u.district_id is not None else None,
            division_id=districts.get(u.district_id).division_id
            if districts.get(u.district_id) is not None
            else u.division_id,
            division_name=(
                division_names.get(districts[u.district_id].division_id)
                if u.district_id in districts and districts[u.district_id].division_id is not None
                else u.division
            ),
        )
        for u in users
    }


def hierarchy_user_to_assignment_user(
    user: HierarchyUserResponse,
    *,
    district_name: str | None,
    division_id: int | None = None,
    division_name: str | None = None,
) -> UserResponse:
    role = user.role if isinstance(user.role, HierarchyRole) else HierarchyRole(str(user.role))
    return UserResponse(
        id=user.id,
        name=user.name,
        role=role,
        parent_id=user.parent_id,
        district_id=user.district_id,
        district=district_name,
        division_id=division_id if division_id is not None else user.division_id,
        division=division_name if division_name is not None else user.division,
        upazilas=[AssignmentUpazilaRef(id=u.id, name=u.name) for u in user.upazilas],
    )
