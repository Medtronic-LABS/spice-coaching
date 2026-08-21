"""Unit tests for assignment assignee resolution (PO expand flag)."""

from __future__ import annotations

import pytest
from mc_contracts.assignments import AssignmentUpazilaRef, UserResponse
from mc_contracts.enums import HierarchyRole
from platform_service.services.assignment_assignees import (
    AssignmentValidationError,
    resolve_assignee_user_ids,
)

PO_ID = 2001
SK_ID = 3001
SK_OTHER_ID = 3002
AM_ID = 1001
SUPER_ADMIN_ID = 9001
DISTRICT_ID = 1
DIVISION_ID = 10
UPAZILA_ID = 1
UPAZILA_OTHER_ID = 2


def _users() -> dict[int, UserResponse]:
    upazila = AssignmentUpazilaRef(id=UPAZILA_ID, name="Lalmonirhat Sadar")
    other = AssignmentUpazilaRef(id=UPAZILA_OTHER_ID, name="Aditmari")
    common = {
        "district_id": DISTRICT_ID,
        "district": "Lalmonirhat",
        "division_id": DIVISION_ID,
        "division": "Rangpur",
    }
    return {
        AM_ID: UserResponse(
            id=AM_ID,
            name="AM",
            role=HierarchyRole.AREA_MANAGER,
            parent_id=None,
            upazilas=[upazila],
            **common,
        ),
        PO_ID: UserResponse(
            id=PO_ID,
            name="PO",
            role=HierarchyRole.PO,
            parent_id=AM_ID,
            upazilas=[upazila],
            **common,
        ),
        SK_ID: UserResponse(
            id=SK_ID,
            name="SK",
            role=HierarchyRole.SHASTIYA_KORMI,
            parent_id=PO_ID,
            upazilas=[upazila],
            **common,
        ),
        SK_OTHER_ID: UserResponse(
            id=SK_OTHER_ID,
            name="SK Other",
            role=HierarchyRole.SHASTIYA_KORMI,
            parent_id=PO_ID + 1,
            upazilas=[other],
            **common,
        ),
        SUPER_ADMIN_ID: UserResponse(
            id=SUPER_ADMIN_ID,
            name="Admin",
            role=HierarchyRole.SUPER_ADMIN,
            parent_id=None,
            district_id=None,
            district=None,
            division_id=None,
            division=None,
            upazilas=[],
        ),
    }


def test_resolve_po_only_by_default() -> None:
    result = resolve_assignee_user_ids(
        user_ids=[PO_ID],
        upazila_ids=None,
        district_ids=None,
        division_ids=None,
        users_by_id=_users(),
    )
    assert result == {PO_ID}


def test_resolve_po_expands_when_flag_true() -> None:
    result = resolve_assignee_user_ids(
        user_ids=[PO_ID],
        upazila_ids=None,
        district_ids=None,
        division_ids=None,
        users_by_id=_users(),
        expand_po_assignees=True,
    )
    assert result == {PO_ID, SK_ID}


def test_resolve_mixed_po_and_sk_without_expand() -> None:
    result = resolve_assignee_user_ids(
        user_ids=[PO_ID, SK_OTHER_ID],
        upazila_ids=None,
        district_ids=None,
        division_ids=None,
        users_by_id=_users(),
        expand_po_assignees=False,
    )
    assert result == {PO_ID, SK_OTHER_ID}


def test_resolve_upazila_unaffected_by_flag() -> None:
    with_flag = resolve_assignee_user_ids(
        user_ids=None,
        upazila_ids=[UPAZILA_ID],
        district_ids=None,
        division_ids=None,
        users_by_id=_users(),
        expand_po_assignees=False,
    )
    without_flag = resolve_assignee_user_ids(
        user_ids=None,
        upazila_ids=[UPAZILA_ID],
        district_ids=None,
        division_ids=None,
        users_by_id=_users(),
        expand_po_assignees=True,
    )
    assert with_flag == without_flag == {PO_ID, SK_ID}


def test_resolve_rejects_area_manager() -> None:
    with pytest.raises(AssignmentValidationError, match="Area Manager"):
        resolve_assignee_user_ids(
            user_ids=[AM_ID],
            upazila_ids=None,
            district_ids=None,
            division_ids=None,
            users_by_id=_users(),
        )


def test_resolve_rejects_super_admin() -> None:
    with pytest.raises(AssignmentValidationError, match="Super Admin"):
        resolve_assignee_user_ids(
            user_ids=[SUPER_ADMIN_ID],
            upazila_ids=None,
            district_ids=None,
            division_ids=None,
            users_by_id=_users(),
        )


def test_resolve_district_includes_all_roles() -> None:
    result = resolve_assignee_user_ids(
        user_ids=None,
        upazila_ids=None,
        district_ids=[DISTRICT_ID],
        division_ids=None,
        users_by_id=_users(),
    )
    assert result == {AM_ID, PO_ID, SK_ID, SK_OTHER_ID}


def test_resolve_division_includes_all_roles() -> None:
    result = resolve_assignee_user_ids(
        user_ids=None,
        upazila_ids=None,
        district_ids=None,
        division_ids=[DIVISION_ID],
        users_by_id=_users(),
    )
    assert result == {AM_ID, PO_ID, SK_ID, SK_OTHER_ID}


def test_resolve_district_unaffected_by_expand_flag() -> None:
    with_flag = resolve_assignee_user_ids(
        user_ids=None,
        upazila_ids=None,
        district_ids=[DISTRICT_ID],
        division_ids=None,
        users_by_id=_users(),
        expand_po_assignees=True,
    )
    without_flag = resolve_assignee_user_ids(
        user_ids=None,
        upazila_ids=None,
        district_ids=[DISTRICT_ID],
        division_ids=None,
        users_by_id=_users(),
        expand_po_assignees=False,
    )
    assert with_flag == without_flag


def test_resolve_combined_district_and_user_ids() -> None:
    result = resolve_assignee_user_ids(
        user_ids=[PO_ID],
        upazila_ids=None,
        district_ids=[DISTRICT_ID],
        division_ids=None,
        users_by_id=_users(),
    )
    assert result == {AM_ID, PO_ID, SK_ID, SK_OTHER_ID}


def test_resolve_requires_at_least_one_input() -> None:
    with pytest.raises(
        AssignmentValidationError,
        match="user_ids, upazila_ids, district_ids, or division_ids must be provided",
    ):
        resolve_assignee_user_ids(
            user_ids=None,
            upazila_ids=None,
            district_ids=None,
            division_ids=None,
            users_by_id=_users(),
        )
