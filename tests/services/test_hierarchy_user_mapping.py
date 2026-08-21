"""Unit tests for hierarchy user → assignment UserResponse mapping."""

from __future__ import annotations

from datetime import UTC, datetime

from mc_contracts.enums import HierarchyRole
from mc_contracts.hierarchy import HierarchyUserResponse
from platform_service.services.hierarchy_geo import non_null_district_ids
from platform_service.services.hierarchy_user_mapping import hierarchy_user_to_assignment_user

SUPER_ADMIN_ID = 9001
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _super_admin_hierarchy_user() -> HierarchyUserResponse:
    return HierarchyUserResponse(
        id=SUPER_ADMIN_ID,
        name="Admin",
        role=HierarchyRole.SUPER_ADMIN,
        parent_id=None,
        district_id=None,
        division_id=None,
        division=None,
        upazilas=[],
        tenant_id=0,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_hierarchy_user_to_assignment_user_null_district() -> None:
    user = _super_admin_hierarchy_user()
    result = hierarchy_user_to_assignment_user(
        user,
        district_name=None,
        division_id=None,
        division_name=None,
    )
    assert result.id == SUPER_ADMIN_ID
    assert result.role == HierarchyRole.SUPER_ADMIN
    assert result.district_id is None
    assert result.district is None
    assert result.division_id is None
    assert result.division is None
    assert result.upazilas == []


def test_non_null_district_ids_excludes_null() -> None:
    users = [
        _super_admin_hierarchy_user(),
        HierarchyUserResponse(
            id=1001,
            name="AM",
            role=HierarchyRole.AREA_MANAGER,
            parent_id=None,
            district_id=42,
            tenant_id=0,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    ]
    assert non_null_district_ids(users) == {42}
