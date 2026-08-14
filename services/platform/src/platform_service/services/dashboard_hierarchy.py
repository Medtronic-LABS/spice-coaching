"""AREA_MANAGER → PO → SHASTIYA_KORMI hierarchy for dashboard scoping.

Loads tenant-scoped users from ``HierarchyService.list_all_users``. True platform
admins (not found as hierarchy roles, or unrestricted) see all users; AM/PO see
descendants (optionally plus self); SK sees self only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mc_contracts.dashboard import DashboardUserSummary
from mc_contracts.enums import HierarchyRole
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.services.hierarchy_service import HierarchyService

_HIERARCHY_SCOPED_ROLES = frozenset(
    {
        HierarchyRole.AREA_MANAGER.value,
        HierarchyRole.PO.value,
        HierarchyRole.SHASTIYA_KORMI.value,
    }
)


@dataclass(frozen=True, slots=True)
class OrgUser:
    id: int
    name: str
    role: str
    district_id: int
    district: str | None
    division_id: int | None
    division: str | None
    upazila_ids: frozenset[int]
    upazila_names: frozenset[str]
    parent_id: int | None


def _role_value(role: HierarchyRole | str) -> str:
    if isinstance(role, HierarchyRole):
        return role.value
    return str(role)


async def org_user_index(
    session: AsyncSession,
    *,
    tenant_id: int,
) -> dict[int, OrgUser]:
    """Map SPICE user id → org user record for the selected tenant."""
    hierarchy = HierarchyService(session)
    users = await hierarchy.list_all_users(tenant_id=tenant_id)
    district_names = await hierarchy.district_names_by_ids(
        {u.district_id for u in users},
        tenant_id=tenant_id,
    )
    districts = await hierarchy.districts_by_ids(
        {u.district_id for u in users},
        tenant_id=tenant_id,
    )
    division_ids = {d.division_id for d in districts.values() if d.division_id is not None}
    division_names = await hierarchy.division_names_by_ids(division_ids, tenant_id=tenant_id)
    out: dict[int, OrgUser] = {}
    for raw in users:
        district = districts.get(raw.district_id)
        division_id = district.division_id if district is not None else raw.division_id
        division_name = division_names.get(division_id) if division_id is not None else raw.division
        out[raw.id] = OrgUser(
            id=raw.id,
            name=raw.name,
            role=_role_value(raw.role),
            district_id=raw.district_id,
            district=district_names.get(raw.district_id),
            division_id=division_id,
            division=division_name,
            upazila_ids=frozenset(u.id for u in raw.upazilas),
            upazila_names=frozenset(u.name for u in raw.upazilas),
            parent_id=raw.parent_id,
        )
    return out


async def resolve_visible_chw_ids(
    session: AsyncSession,
    viewer_id: int | None,
    *,
    tenant_id: int,
    unrestricted: bool = False,
    include_self: bool = True,
) -> frozenset[int] | None:
    """Return chw_ids the viewer may see, or None when unrestricted (all users).

    - ``unrestricted=True`` (super/head-office/auth-off): no chw filter.
    - AREA_MANAGER: descendant POs and SKs; include self when ``include_self``.
    - PO: direct SK children; include self when ``include_self``.
    - SHASTIYA_KORMI: self only (ignores ``include_self``).
    - Viewer id missing from the map and not unrestricted: empty set (deny) when
      ``viewer_id`` is None; unknown id → unrestricted (platform admin).
    """
    if unrestricted:
        return None
    if viewer_id is None:
        return frozenset()

    by_id = await org_user_index(session, tenant_id=tenant_id)
    viewer = by_id.get(viewer_id)
    if viewer is None:
        # Not in hierarchy map — treat as platform admin with full visibility.
        return None

    if viewer.role == HierarchyRole.AREA_MANAGER.value:
        visible: set[int] = {viewer.id} if include_self else set()
        po_ids = {
            u.id for u in by_id.values() if u.role == HierarchyRole.PO.value and u.parent_id == viewer.id
        }
        visible.update(po_ids)
        visible.update(
            u.id
            for u in by_id.values()
            if u.role == HierarchyRole.SHASTIYA_KORMI.value and u.parent_id in po_ids
        )
        return frozenset(visible)

    if viewer.role == HierarchyRole.PO.value:
        visible = {viewer.id} if include_self else set()
        visible.update(
            u.id
            for u in by_id.values()
            if u.role == HierarchyRole.SHASTIYA_KORMI.value and u.parent_id == viewer.id
        )
        return frozenset(visible)

    # SK or unknown role in map — always self only.
    return frozenset({viewer.id})


def focus_subtree_ids(by_id: dict[int, OrgUser], user_id: int) -> set[int]:
    """Role-aware subtree for a document-usage / dashboard focus user.

    AREA_MANAGER → self + descendant POs + their SKs; PO → self + child SKs;
    SHASTIYA_KORMI / unknown-in-map role → self only; missing user → empty.
    """
    focus = by_id.get(user_id)
    if focus is None:
        return set()

    if focus.role == HierarchyRole.AREA_MANAGER.value:
        po_ids = {u.id for u in by_id.values() if u.role == HierarchyRole.PO.value and u.parent_id == user_id}
        sk_ids = {
            u.id
            for u in by_id.values()
            if u.role == HierarchyRole.SHASTIYA_KORMI.value and u.parent_id in po_ids
        }
        return {user_id, *po_ids, *sk_ids}

    if focus.role == HierarchyRole.PO.value:
        sk_ids = {
            u.id
            for u in by_id.values()
            if u.role == HierarchyRole.SHASTIYA_KORMI.value and u.parent_id == user_id
        }
        return {user_id, *sk_ids}

    return {user_id}


async def apply_document_usage_filters(
    session: AsyncSession,
    visible_chw_ids: frozenset[int] | None,
    *,
    tenant_id: int,
    user_id: int | None = None,
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    index: dict[int, OrgUser] | None = None,
) -> frozenset[int] | None:
    """Intersect hierarchy visibility with user/division/district/upazila filters.

    Optional ``user_id`` is a role-aware focus (same grain as former ``po_id`` /
    ``sk_id``): PO → PO+SKs, AM → AM+descendants, SK → that user. Geography
    filters resolve against the org user map so scope stays consistent with
    hierarchy. Returns None when still unrestricted (no chw filter needed).
    Returns an empty frozenset when filters yield no matching users.
    """
    by_id = index if index is not None else await org_user_index(session, tenant_id=tenant_id)
    candidates: set[int] | None
    if visible_chw_ids is None:
        candidates = None
    else:
        candidates = set(visible_chw_ids)

    def _intersect(ids: set[int]) -> None:
        nonlocal candidates
        if candidates is None:
            candidates = set(ids)
        else:
            candidates &= ids

    if user_id is not None:
        _intersect(focus_subtree_ids(by_id, user_id))

    if division is not None and division.strip():
        needle = division.strip().casefold()
        division_ids = {
            u.id for u in by_id.values() if u.division is not None and u.division.casefold() == needle
        }
        _intersect(division_ids)

    if district is not None and district.strip():
        needle = district.strip().casefold()
        district_ids = {
            u.id for u in by_id.values() if u.district is not None and u.district.casefold() == needle
        }
        _intersect(district_ids)

    if upazila is not None and upazila.strip():
        needle = upazila.strip().casefold()
        upazila_ids = {
            u.id for u in by_id.values() if any(name.casefold() == needle for name in u.upazila_names)
        }
        _intersect(upazila_ids)

    if candidates is None:
        return None
    return frozenset(candidates)


async def resolve_geography_chw_ids(
    session: AsyncSession,
    *,
    tenant_id: int,
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
) -> frozenset[int] | None:
    """Return user ids matching optional division/district/upazila name filters, or None when unset."""
    return await apply_document_usage_filters(
        session,
        None,
        tenant_id=tenant_id,
        division=division,
        district=district,
        upazila=upazila,
    )


def filter_users_by_chw_ids(
    users: list[OrgUser],
    allowed_chw_ids: frozenset[int] | None,
) -> list[OrgUser]:
    """Keep org users whose id is in ``allowed_chw_ids``; pass-through when None."""
    if allowed_chw_ids is None:
        return users
    return [u for u in users if u.id in allowed_chw_ids]


def user_display(user_id: int, index: dict[int, OrgUser] | None = None) -> dict[str, Any]:
    """Name / role / geo display fields for a chw_id (nulls when unknown)."""
    if index is None:
        return {
            "user_name": None,
            "user_role": None,
            "division": None,
            "district": None,
            "upazila": None,
        }
    user = index.get(user_id)
    if user is None:
        return {
            "user_name": None,
            "user_role": None,
            "division": None,
            "district": None,
            "upazila": None,
        }
    # Prefer a stable single upazila name for display (sorted).
    upazila_name = next(iter(sorted(user.upazila_names)), None)
    return {
        "user_name": user.name or None,
        "user_role": user.role or None,
        "division": user.division,
        "district": user.district,
        "upazila": upazila_name,
    }


def dashboard_user_summary(
    chw_id: int | None,
    index: dict[int, OrgUser] | None = None,
) -> DashboardUserSummary:
    """Build contract user summary for a CHW id (null fields when unknown)."""
    if chw_id is None:
        return DashboardUserSummary()
    display = user_display(chw_id, index)
    return DashboardUserSummary(
        user_id=chw_id,
        user_name=display["user_name"],
        user_role=display["user_role"],
        division=display["division"],
        district=display["district"],
        upazila=display["upazila"],
    )


def is_hierarchy_scoped_role(role: str) -> bool:
    return role in _HIERARCHY_SCOPED_ROLES


def child_role_for(focus_role: str | None) -> str | None:
    """Next hierarchy role under ``focus_role``; ``None`` focus = synthetic Admin root → AMs."""
    if focus_role is None:
        return HierarchyRole.AREA_MANAGER.value
    if focus_role == HierarchyRole.AREA_MANAGER.value:
        return HierarchyRole.PO.value
    if focus_role == HierarchyRole.PO.value:
        return HierarchyRole.SHASTIYA_KORMI.value
    return None


def member_role_at_depth(focus_role: str | None, depth: int) -> str | None:
    """Hierarchy role for team-activity members at ``depth`` under ``focus_role``.

    ``depth=0`` is the direct child role (same as ``child_role_for``). Each
    increment walks one level deeper. Returns ``None`` when ``depth`` is past
    the leaf under the focus (caller should map to 422).
    """
    if depth < 0:
        return None
    role: str | None = child_role_for(focus_role)
    for _ in range(depth):
        if role is None:
            return None
        role = child_role_for(role)
    return role


def descendants_with_role(
    by_id: dict[int, OrgUser],
    focus_id: int | None,
    focus_role: str | None,
    member_role: str,
) -> list[OrgUser]:
    """Users with ``member_role`` under the effective team-activity focus.

    Orphan exclusion matches ``sks_under_focus``: POs must parent under an AM
    (for Admin root), and SKs must parent under such POs.
    """
    am_role = HierarchyRole.AREA_MANAGER.value
    po_role = HierarchyRole.PO.value
    sk_role = HierarchyRole.SHASTIYA_KORMI.value

    if member_role == sk_role:
        return sks_under_focus(by_id, focus_id, focus_role)

    if focus_role is None:
        # Synthetic Admin root.
        if member_role == am_role:
            return direct_children(by_id, None, am_role)
        if member_role == po_role:
            am_ids = {u.id for u in by_id.values() if u.role == am_role}
            return [u for u in by_id.values() if u.role == po_role and u.parent_id in am_ids]
        return []

    if focus_role == am_role and focus_id is not None and member_role == po_role:
        return direct_children(by_id, focus_id, po_role)

    return []


def is_team_activity_descendant(
    by_id: dict[int, OrgUser],
    viewer_id: int | None,
    target_id: int,
    *,
    unrestricted: bool,
) -> bool:
    """Whether ``target_id`` may be a team-activity focus for the viewer.

    Unrestricted: any user present in the org map. Restricted: target is the
    viewer or a descendant in the AM→PO→SK tree. Unknown target → False.
    """
    target = by_id.get(target_id)
    if target is None:
        return False
    if unrestricted:
        return True
    if viewer_id is None:
        return False
    if target_id == viewer_id:
        return True

    viewer = by_id.get(viewer_id)
    if viewer is None:
        return False

    if viewer.role == HierarchyRole.AREA_MANAGER.value:
        if target.role == HierarchyRole.PO.value and target.parent_id == viewer_id:
            return True
        if target.role == HierarchyRole.SHASTIYA_KORMI.value:
            po = by_id.get(target.parent_id) if target.parent_id is not None else None
            return po is not None and po.role == HierarchyRole.PO.value and po.parent_id == viewer_id
        return False

    if viewer.role == HierarchyRole.PO.value:
        return target.role == HierarchyRole.SHASTIYA_KORMI.value and target.parent_id == viewer_id

    return False


def direct_children(
    by_id: dict[int, OrgUser],
    parent_id: int | None,
    child_role: str,
) -> list[OrgUser]:
    """Direct children of ``parent_id`` with ``child_role``.

    When ``parent_id`` is None (synthetic Admin root), returns all users with
    ``child_role`` (typically all Area Managers).
    """
    if parent_id is None:
        return [u for u in by_id.values() if u.role == child_role]
    return [u for u in by_id.values() if u.role == child_role and u.parent_id == parent_id]


def sks_under_focus(
    by_id: dict[int, OrgUser],
    focus_user_id: int | None,
    focus_role: str | None,
) -> list[OrgUser]:
    """SKs under the effective focus root (orphan SKs excluded for AM/Admin trees).

    - Synthetic root (``focus_role`` None): SKs whose PO parent is under some AM.
    - AM: SKs under that AM's POs.
    - PO: direct SK children.
    - SK: that SK alone.
    """
    sk_role = HierarchyRole.SHASTIYA_KORMI.value
    po_role = HierarchyRole.PO.value
    am_role = HierarchyRole.AREA_MANAGER.value

    if focus_role == sk_role and focus_user_id is not None:
        sk = by_id.get(focus_user_id)
        return [sk] if sk is not None and sk.role == sk_role else []

    if focus_role == po_role and focus_user_id is not None:
        return [u for u in by_id.values() if u.role == sk_role and u.parent_id == focus_user_id]

    if focus_role == am_role and focus_user_id is not None:
        po_ids = {u.id for u in by_id.values() if u.role == po_role and u.parent_id == focus_user_id}
        return [u for u in by_id.values() if u.role == sk_role and u.parent_id in po_ids]

    # Synthetic unrestricted root: SKs under all AMs' POs (exclude orphans).
    am_ids = {u.id for u in by_id.values() if u.role == am_role}
    po_ids = {u.id for u in by_id.values() if u.role == po_role and u.parent_id in am_ids}
    return [u for u in by_id.values() if u.role == sk_role and u.parent_id in po_ids]


def sks_under_member(
    by_id: dict[int, OrgUser],
    member: OrgUser,
) -> list[OrgUser]:
    """SKs under one current-level member (AM → subtree; PO → direct; SK → self)."""
    return sks_under_focus(by_id, member.id, member.role)
