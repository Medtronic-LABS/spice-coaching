"""Unit tests for hierarchy tree validation rules including upazilas."""

from __future__ import annotations

import pytest
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from platform_service.db.models.hierarchy_user import (
    ROLE_AREA_MANAGER,
    ROLE_PO,
    ROLE_SHASTIYA_KORMI,
)
from platform_service.services.hierarchy_validator import (
    DistrictSnapshot,
    ParentSnapshot,
    UpazilaSnapshot,
    expected_parent_role,
    validate_hierarchy_user,
)


def test_expected_parent_role() -> None:
    assert expected_parent_role(ROLE_AREA_MANAGER) is None
    assert expected_parent_role(ROLE_PO) == ROLE_AREA_MANAGER
    assert expected_parent_role(ROLE_SHASTIYA_KORMI) == ROLE_PO


def test_area_manager_without_parent_ok() -> None:
    validate_hierarchy_user(
        role=ROLE_AREA_MANAGER,
        parent_id=None,
        district_id=1,
        tenant_id=7,
        upazila_ids=[101],
        parent=None,
        district=DistrictSnapshot(id=1, tenant_id=7),
        upazilas_map={101: UpazilaSnapshot(id=101, district_id=1, tenant_id=7)},
    )


def test_area_manager_with_parent_rejected() -> None:
    with pytest.raises(AppError) as exc:
        validate_hierarchy_user(
            role=ROLE_AREA_MANAGER,
            parent_id=99,
            district_id=1,
            tenant_id=7,
            upazila_ids=[],
            parent=ParentSnapshot(
                id=99, role=ROLE_AREA_MANAGER, district_id=1, tenant_id=7, upazila_ids=set()
            ),
            district=DistrictSnapshot(id=1, tenant_id=7),
        )
    assert exc.value.code == ErrorCode.HIERARCHY_PARENT_INVALID.value


def test_po_under_am_ok() -> None:
    validate_hierarchy_user(
        role=ROLE_PO,
        parent_id=10,
        district_id=1,
        tenant_id=7,
        upazila_ids=[101],
        parent=ParentSnapshot(
            id=10, role=ROLE_AREA_MANAGER, district_id=1, tenant_id=7, upazila_ids={101, 102}
        ),
        district=DistrictSnapshot(id=1, tenant_id=7),
        upazilas_map={101: UpazilaSnapshot(id=101, district_id=1, tenant_id=7)},
    )


def test_child_upazila_not_in_parent_rejected() -> None:
    with pytest.raises(AppError) as exc:
        validate_hierarchy_user(
            role=ROLE_PO,
            parent_id=10,
            district_id=1,
            tenant_id=7,
            upazila_ids=[103],
            parent=ParentSnapshot(
                id=10, role=ROLE_AREA_MANAGER, district_id=1, tenant_id=7, upazila_ids={101, 102}
            ),
            district=DistrictSnapshot(id=1, tenant_id=7),
            upazilas_map={103: UpazilaSnapshot(id=103, district_id=1, tenant_id=7)},
        )
    assert exc.value.code == ErrorCode.HIERARCHY_UPAZILA_INVALID.value


def test_upazila_district_mismatch_rejected() -> None:
    with pytest.raises(AppError) as exc:
        validate_hierarchy_user(
            role=ROLE_AREA_MANAGER,
            parent_id=None,
            district_id=1,
            tenant_id=7,
            upazila_ids=[101],
            parent=None,
            district=DistrictSnapshot(id=1, tenant_id=7),
            upazilas_map={101: UpazilaSnapshot(id=101, district_id=2, tenant_id=7)},
        )
    assert exc.value.code == ErrorCode.HIERARCHY_UPAZILA_INVALID.value


def test_po_under_po_rejected() -> None:
    with pytest.raises(AppError) as exc:
        validate_hierarchy_user(
            role=ROLE_PO,
            parent_id=11,
            district_id=1,
            tenant_id=7,
            upazila_ids=[],
            parent=ParentSnapshot(id=11, role=ROLE_PO, district_id=1, tenant_id=7, upazila_ids=set()),
            district=DistrictSnapshot(id=1, tenant_id=7),
        )
    assert exc.value.code == ErrorCode.HIERARCHY_PARENT_INVALID.value


def test_sk_under_po_ok() -> None:
    validate_hierarchy_user(
        role=ROLE_SHASTIYA_KORMI,
        parent_id=20,
        district_id=1,
        tenant_id=7,
        upazila_ids=[101],
        parent=ParentSnapshot(id=20, role=ROLE_PO, district_id=1, tenant_id=7, upazila_ids={101}),
        district=DistrictSnapshot(id=1, tenant_id=7),
        upazilas_map={101: UpazilaSnapshot(id=101, district_id=1, tenant_id=7)},
    )


def test_cross_district_parent_rejected() -> None:
    with pytest.raises(AppError) as exc:
        validate_hierarchy_user(
            role=ROLE_PO,
            parent_id=10,
            district_id=2,
            tenant_id=7,
            upazila_ids=[],
            parent=ParentSnapshot(
                id=10, role=ROLE_AREA_MANAGER, district_id=1, tenant_id=7, upazila_ids=set()
            ),
            district=DistrictSnapshot(id=2, tenant_id=7),
        )
    assert exc.value.code == ErrorCode.HIERARCHY_PARENT_INVALID.value


def test_tenant_mismatch_rejected() -> None:
    with pytest.raises(AppError) as exc:
        validate_hierarchy_user(
            role=ROLE_AREA_MANAGER,
            parent_id=None,
            district_id=1,
            tenant_id=7,
            upazila_ids=[],
            parent=None,
            district=DistrictSnapshot(id=1, tenant_id=9),
        )
    assert exc.value.code == ErrorCode.HIERARCHY_PARENT_INVALID.value


def test_missing_district_rejected() -> None:
    with pytest.raises(AppError) as exc:
        validate_hierarchy_user(
            role=ROLE_AREA_MANAGER,
            parent_id=None,
            district_id=1,
            tenant_id=7,
            upazila_ids=[],
            parent=None,
            district=None,
        )
    assert exc.value.code == ErrorCode.HIERARCHY_DISTRICT_NOT_FOUND.value


def test_unsupported_role_rejected() -> None:
    with pytest.raises(AppError) as exc:
        validate_hierarchy_user(
            role="UNKNOWN",
            parent_id=None,
            district_id=1,
            tenant_id=7,
            upazila_ids=[],
            parent=None,
            district=DistrictSnapshot(id=1, tenant_id=7),
        )
    assert exc.value.code == ErrorCode.HIERARCHY_ROLE_MISMATCH.value
