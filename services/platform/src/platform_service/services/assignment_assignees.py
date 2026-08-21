"""Shared assignee resolution for module and document assignments."""

from __future__ import annotations

from mc_contracts.assignments import UserResponse
from mc_contracts.enums import HierarchyRole
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.services.hierarchy_service import HierarchyService


class AssignmentValidationError(Exception):
    """Raised when assignment validation fails."""

    pass


def _expand_po_assignees(po_id: int, users_by_id: dict[int, UserResponse]) -> set[int]:
    assignee_ids = {po_id}
    for user in users_by_id.values():
        if user.parent_id == po_id and user.role == HierarchyRole.SHASTIYA_KORMI:
            assignee_ids.add(user.id)
    return assignee_ids


def _users_in_upazila(
    upazila_id: int,
    users_by_id: dict[int, UserResponse],
) -> set[int]:
    assignee_ids: set[int] = set()
    for user in users_by_id.values():
        if user.role == HierarchyRole.AREA_MANAGER:
            continue
        if user.role not in (HierarchyRole.PO, HierarchyRole.SHASTIYA_KORMI):
            continue
        if any(ref.id == upazila_id for ref in user.upazilas):
            assignee_ids.add(user.id)
    return assignee_ids


def _users_in_district(
    district_id: int,
    users_by_id: dict[int, UserResponse],
) -> set[int]:
    return {
        user.id
        for user in users_by_id.values()
        if user.district_id is not None and user.district_id == district_id
    }


def _users_in_division(
    division_id: int,
    users_by_id: dict[int, UserResponse],
) -> set[int]:
    return {
        user.id
        for user in users_by_id.values()
        if user.division_id is not None and user.division_id == division_id
    }


async def validate_geography_assignment_ids(
    session: AsyncSession,
    *,
    upazila_ids: list[int] | None,
    district_ids: list[int] | None,
    division_ids: list[int] | None,
    tenant_id: int,
) -> None:
    """Ensure requested upazila, district, and division ids exist in the tenant."""
    hierarchy = HierarchyService(session)
    for upazila_id in upazila_ids or []:
        try:
            await hierarchy.get_upazila(upazila_id, tenant_id=tenant_id)
        except AppError as exc:
            raise AssignmentValidationError(str(exc.detail)) from exc
    for district_id in district_ids or []:
        try:
            await hierarchy.get_district(district_id, tenant_id=tenant_id)
        except AppError as exc:
            raise AssignmentValidationError(str(exc.detail)) from exc
    for division_id in division_ids or []:
        try:
            await hierarchy.get_division(division_id, tenant_id=tenant_id)
        except AppError as exc:
            raise AssignmentValidationError(str(exc.detail)) from exc


def resolve_assignee_user_ids(
    *,
    user_ids: list[int] | None,
    upazila_ids: list[int] | None,
    district_ids: list[int] | None,
    division_ids: list[int] | None,
    users_by_id: dict[int, UserResponse],
    allow_empty: bool = False,
    expand_po_assignees: bool = False,
) -> set[int]:
    """Resolve assignment inputs into concrete assignee user ids.

    PO entries in ``user_ids`` are assigned to the PO only unless
    ``expand_po_assignees`` is true (then the PO plus their direct SK children).
    Upazila targeting is unaffected by this flag. District and division inputs
    expand to all hierarchy users in that geography, including Area Managers.
    """
    resolved_user_ids = user_ids or []
    resolved_upazila_ids = upazila_ids or []
    resolved_district_ids = district_ids or []
    resolved_division_ids = division_ids or []
    if (
        not resolved_user_ids
        and not resolved_upazila_ids
        and not resolved_district_ids
        and not resolved_division_ids
    ):
        if allow_empty:
            return set()
        raise AssignmentValidationError(
            "user_ids, upazila_ids, district_ids, or division_ids must be provided"
        )

    assignee_ids: set[int] = set()

    for user_id in resolved_user_ids:
        user = users_by_id.get(user_id)
        if user is None:
            raise AssignmentValidationError(f"User with ID {user_id} not found")
        if user.role == HierarchyRole.AREA_MANAGER:
            raise AssignmentValidationError(
                f"User with ID {user_id} is an Area Manager and cannot be assigned"
            )
        if user.role == HierarchyRole.SUPER_ADMIN:
            raise AssignmentValidationError(f"User with ID {user_id} is a Super Admin and cannot be assigned")
        if user.role == HierarchyRole.PO:
            if expand_po_assignees:
                assignee_ids.update(_expand_po_assignees(user_id, users_by_id))
            else:
                assignee_ids.add(user_id)
        elif user.role == HierarchyRole.SHASTIYA_KORMI:
            assignee_ids.add(user_id)
        else:
            raise AssignmentValidationError(f"User with ID {user_id} has an unsupported role")

    for upazila_id in resolved_upazila_ids:
        assignee_ids.update(_users_in_upazila(upazila_id, users_by_id))

    for district_id in resolved_district_ids:
        assignee_ids.update(_users_in_district(district_id, users_by_id))

    for division_id in resolved_division_ids:
        assignee_ids.update(_users_in_division(division_id, users_by_id))

    return assignee_ids
