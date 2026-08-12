"""Shared validation rules for district / users hierarchy writes.

Mirrored by the PostgreSQL ``enforce_users_hierarchy`` trigger in migration 0059.
"""

from __future__ import annotations

from dataclasses import dataclass

from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError

from platform_service.db.models.hierarchy_user import (
    HIERARCHY_ROLES,
    ROLE_AREA_MANAGER,
    ROLE_PO,
    ROLE_SHASTIYA_KORMI,
)

_EXPECTED_PARENT_ROLE: dict[str, str] = {
    ROLE_PO: ROLE_AREA_MANAGER,
    ROLE_SHASTIYA_KORMI: ROLE_PO,
}


@dataclass(frozen=True, slots=True)
class ParentSnapshot:
    """Minimal parent fields needed to validate a child row."""

    id: int
    role: str
    district_id: int
    tenant_id: int
    upazila_ids: set[int]


@dataclass(frozen=True, slots=True)
class DistrictSnapshot:
    """Minimal district fields needed to validate a user row."""

    id: int
    tenant_id: int


@dataclass(frozen=True, slots=True)
class UpazilaSnapshot:
    """Minimal upazila fields needed for validation."""

    id: int
    district_id: int
    tenant_id: int


def expected_parent_role(child_role: str) -> str | None:
    """Return the required parent role for ``child_role``, or None for AM."""
    return _EXPECTED_PARENT_ROLE.get(child_role)


def validate_hierarchy_user(
    *,
    role: str,
    parent_id: int | None,
    district_id: int,
    tenant_id: int,
    upazila_ids: list[int],
    parent: ParentSnapshot | None,
    district: DistrictSnapshot | None,
    upazilas_map: dict[int, UpazilaSnapshot] | None = None,
) -> None:
    """Raise ``AppError`` when tree / tenancy invariants or upazila constraints are violated."""
    if role not in HIERARCHY_ROLES:
        raise AppError(
            ErrorCode.HIERARCHY_ROLE_MISMATCH.value,
            f"Unsupported hierarchy role '{role}'.",
            status=400,
        )

    if district is None:
        raise AppError(
            ErrorCode.HIERARCHY_DISTRICT_NOT_FOUND.value,
            f"District '{district_id}' not found.",
            status=404,
        )

    if district.tenant_id != tenant_id:
        raise AppError(
            ErrorCode.HIERARCHY_PARENT_INVALID.value,
            (f"User tenant_id {tenant_id} does not match district tenant_id {district.tenant_id}."),
            status=400,
        )

    if upazilas_map is not None:
        for uid in upazila_ids:
            upazila = upazilas_map.get(uid)
            if upazila is None:
                raise AppError(
                    ErrorCode.HIERARCHY_UPAZILA_NOT_FOUND.value,
                    f"Upazila '{uid}' not found.",
                    status=404,
                )
            if upazila.district_id != district_id or upazila.tenant_id != tenant_id:
                raise AppError(
                    ErrorCode.HIERARCHY_UPAZILA_INVALID.value,
                    f"Upazila '{uid}' does not belong to district '{district_id}' or tenant '{tenant_id}'.",
                    status=400,
                )

    if role == ROLE_AREA_MANAGER:
        if parent_id is not None:
            raise AppError(
                ErrorCode.HIERARCHY_PARENT_INVALID.value,
                "AREA_MANAGER must have parent_id NULL.",
                status=400,
            )
        return

    if parent_id is None:
        raise AppError(
            ErrorCode.HIERARCHY_PARENT_INVALID.value,
            f"Role '{role}' requires a parent_id.",
            status=400,
        )

    if parent is None:
        raise AppError(
            ErrorCode.HIERARCHY_PARENT_INVALID.value,
            f"Parent user '{parent_id}' not found.",
            status=400,
        )

    if parent.district_id != district_id:
        raise AppError(
            ErrorCode.HIERARCHY_PARENT_INVALID.value,
            (f"Parent district_id {parent.district_id} does not match child district_id {district_id}."),
            status=400,
        )

    if parent.tenant_id != tenant_id:
        raise AppError(
            ErrorCode.HIERARCHY_PARENT_INVALID.value,
            (f"Parent tenant_id {parent.tenant_id} does not match child tenant_id {tenant_id}."),
            status=400,
        )

    required = _EXPECTED_PARENT_ROLE[role]
    if parent.role != required:
        raise AppError(
            ErrorCode.HIERARCHY_PARENT_INVALID.value,
            f"Role '{role}' requires parent role '{required}', got '{parent.role}'.",
            status=400,
        )

    for uid in upazila_ids:
        if uid not in parent.upazila_ids:
            raise AppError(
                ErrorCode.HIERARCHY_UPAZILA_INVALID.value,
                f"Upazila '{uid}' is not assigned to parent user '{parent.id}'. Child user upazilas must belong to parent's upazilas.",
                status=400,
            )
