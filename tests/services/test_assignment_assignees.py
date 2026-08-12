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


def _users() -> dict[int, UserResponse]:
    upazila = AssignmentUpazilaRef(id=1, name="Lalmonirhat Sadar")
    other = AssignmentUpazilaRef(id=2, name="Aditmari")
    return {
        AM_ID: UserResponse(
            id=AM_ID,
            name="AM",
            role=HierarchyRole.AREA_MANAGER,
            parent_id=None,
            district_id=1,
            district="Lalmonirhat",
            upazilas=[upazila],
        ),
        PO_ID: UserResponse(
            id=PO_ID,
            name="PO",
            role=HierarchyRole.PO,
            parent_id=AM_ID,
            district_id=1,
            district="Lalmonirhat",
            upazilas=[upazila],
        ),
        SK_ID: UserResponse(
            id=SK_ID,
            name="SK",
            role=HierarchyRole.SHASTIYA_KORMI,
            parent_id=PO_ID,
            district_id=1,
            district="Lalmonirhat",
            upazilas=[upazila],
        ),
        SK_OTHER_ID: UserResponse(
            id=SK_OTHER_ID,
            name="SK Other",
            role=HierarchyRole.SHASTIYA_KORMI,
            parent_id=PO_ID + 1,
            district_id=1,
            district="Lalmonirhat",
            upazilas=[other],
        ),
    }


def test_resolve_po_only_by_default() -> None:
    result = resolve_assignee_user_ids(user_ids=[PO_ID], upazilas=None, users_by_id=_users())
    assert result == {PO_ID}


def test_resolve_po_expands_when_flag_true() -> None:
    result = resolve_assignee_user_ids(
        user_ids=[PO_ID],
        upazilas=None,
        users_by_id=_users(),
        expand_po_assignees=True,
    )
    assert result == {PO_ID, SK_ID}


def test_resolve_mixed_po_and_sk_without_expand() -> None:
    result = resolve_assignee_user_ids(
        user_ids=[PO_ID, SK_OTHER_ID],
        upazilas=None,
        users_by_id=_users(),
        expand_po_assignees=False,
    )
    assert result == {PO_ID, SK_OTHER_ID}


def test_resolve_upazila_unaffected_by_flag() -> None:
    with_flag = resolve_assignee_user_ids(
        user_ids=None,
        upazilas=["Lalmonirhat Sadar"],
        users_by_id=_users(),
        expand_po_assignees=False,
    )
    without_flag = resolve_assignee_user_ids(
        user_ids=None,
        upazilas=["Lalmonirhat Sadar"],
        users_by_id=_users(),
        expand_po_assignees=True,
    )
    assert with_flag == without_flag == {PO_ID, SK_ID}


def test_resolve_rejects_area_manager() -> None:
    with pytest.raises(AssignmentValidationError, match="Area Manager"):
        resolve_assignee_user_ids(user_ids=[AM_ID], upazilas=None, users_by_id=_users())
