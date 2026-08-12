"""Shared assignee resolution for module and document assignments."""

from __future__ import annotations

from mc_contracts.assignments import UserResponse
from mc_contracts.enums import HierarchyRole


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
    upazila: str,
    users_by_id: dict[int, UserResponse],
) -> set[int]:
    needle = upazila.strip().casefold()
    if not needle:
        return set()

    assignee_ids: set[int] = set()
    for user in users_by_id.values():
        if user.role == HierarchyRole.AREA_MANAGER:
            continue
        if user.role not in (HierarchyRole.PO, HierarchyRole.SHASTIYA_KORMI):
            continue
        if any(ref.name.casefold() == needle for ref in user.upazilas):
            assignee_ids.add(user.id)
    return assignee_ids


def resolve_assignee_user_ids(
    *,
    user_ids: list[int] | None,
    upazilas: list[str] | None,
    users_by_id: dict[int, UserResponse],
    allow_empty: bool = False,
    expand_po_assignees: bool = False,
) -> set[int]:
    """Resolve explicit user_ids and upazila names into concrete PO/SK assignee ids.

    PO entries in ``user_ids`` are assigned to the PO only unless
    ``expand_po_assignees`` is true (then the PO plus their direct SK children).
    Upazila targeting is unaffected by this flag.
    """
    resolved_user_ids = user_ids or []
    resolved_upazilas = upazilas or []
    if not resolved_user_ids and not resolved_upazilas:
        if allow_empty:
            return set()
        raise AssignmentValidationError("user_ids or upazilas must be provided")

    assignee_ids: set[int] = set()

    for user_id in resolved_user_ids:
        user = users_by_id.get(user_id)
        if user is None:
            raise AssignmentValidationError(f"User with ID {user_id} not found")
        if user.role == HierarchyRole.AREA_MANAGER:
            raise AssignmentValidationError(
                f"User with ID {user_id} is an Area Manager and cannot be assigned"
            )
        if user.role == HierarchyRole.PO:
            if expand_po_assignees:
                assignee_ids.update(_expand_po_assignees(user_id, users_by_id))
            else:
                assignee_ids.add(user_id)
        elif user.role == HierarchyRole.SHASTIYA_KORMI:
            assignee_ids.add(user_id)
        else:
            raise AssignmentValidationError(f"User with ID {user_id} has an unsupported role")

    for upazila in resolved_upazilas:
        assignee_ids.update(_users_in_upazila(upazila, users_by_id))

    return assignee_ids
