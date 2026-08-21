"""Shared hierarchy seed helpers for tests that need AM → PO → SK trees."""

from __future__ import annotations

from dataclasses import dataclass

from mc_contracts.enums import HierarchyRole
from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.district import District
from platform_service.db.models.division import Division
from platform_service.db.models.hierarchy_user import ROLE_SUPER_ADMIN, HierarchyUser
from platform_service.db.models.role import Role
from platform_service.db.models.upazila import Upazila
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Stable IDs used across assignment / sync / demand / document-usage tests.
AM_ID = 1001
PO_ID = 2001
PO_OTHER_ID = 2002
SK_ID = 3001
SK_OTHER_ID = 3002

_DEFAULT_ROLE_CODES = (
    HierarchyRole.AREA_MANAGER.value,
    HierarchyRole.PO.value,
    HierarchyRole.SHASTIYA_KORMI.value,
    ROLE_SUPER_ADMIN,
)


async def ensure_hierarchy_roles(session: AsyncSession) -> dict[str, Role]:
    """Return role rows keyed by code, inserting any missing catalog entries."""
    existing = {row.code: row for row in (await session.execute(select(Role))).scalars().all()}
    created = False
    for code in _DEFAULT_ROLE_CODES:
        if code not in existing:
            row = Role(code=code)
            session.add(row)
            existing[code] = row
            created = True
    if created:
        await session.flush()
    return existing


async def hierarchy_user(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    role: str,
    district_id: int,
    tenant_id: int,
    parent_id: int | None = None,
    created_by: int | None = None,
    updated_by: int | None = None,
) -> HierarchyUser:
    """Build a ``HierarchyUser`` with ``role_id`` resolved from the role catalog."""
    roles = await ensure_hierarchy_roles(session)
    role_row = roles[role]
    user = HierarchyUser(
        id=user_id,
        name=name,
        role_id=role_row.id,
        parent_id=parent_id,
        district_id=district_id,
        tenant_id=tenant_id,
        created_by=created_by,
        updated_by=updated_by,
    )
    user.role_row = role_row
    return user


@dataclass(frozen=True, slots=True)
class HierarchySeed:
    tenant_id: int
    division_id: int
    division_name: str
    district_id: int
    upazila_id: int
    upazila_other_id: int
    upazila_name: str
    upazila_other_name: str
    district_name: str
    am_id: int
    po_id: int
    po_other_id: int
    sk_id: int
    sk_other_id: int


async def seed_basic_hierarchy(
    session: AsyncSession,
    *,
    tenant_id: int = DEFAULT_TENANT_ID,
    division_name: str = "Rangpur",
    district_name: str = "Lalmonirhat",
    upazila_name: str = "Lalmonirhat Sadar",
    upazila_other_name: str = "Aditmari",
    am_id: int = AM_ID,
    po_id: int = PO_ID,
    po_other_id: int = PO_OTHER_ID,
    sk_id: int = SK_ID,
    sk_other_id: int = SK_OTHER_ID,
) -> HierarchySeed:
    """Insert division + district + upazilas + AM → two POs → two SKs (one under each PO)."""
    await ensure_hierarchy_roles(session)

    division = Division(
        name=division_name,
        tenant_id=tenant_id,
        created_by=None,
        updated_by=None,
    )
    session.add(division)
    await session.flush()

    district = District(
        name=district_name,
        division_id=division.id,
        tenant_id=tenant_id,
        created_by=None,
        updated_by=None,
    )
    session.add(district)
    await session.flush()

    upazila = Upazila(
        name=upazila_name,
        district_id=district.id,
        tenant_id=tenant_id,
        created_by=None,
        updated_by=None,
    )
    upazila_other = Upazila(
        name=upazila_other_name,
        district_id=district.id,
        tenant_id=tenant_id,
        created_by=None,
        updated_by=None,
    )
    session.add(upazila)
    session.add(upazila_other)
    await session.flush()

    am = await hierarchy_user(
        session,
        user_id=am_id,
        name="Test Area Manager",
        role=HierarchyRole.AREA_MANAGER.value,
        parent_id=None,
        district_id=district.id,
        tenant_id=tenant_id,
    )
    am.upazilas = []
    session.add(am)
    await session.flush()

    po = await hierarchy_user(
        session,
        user_id=po_id,
        name="Test PO",
        role=HierarchyRole.PO.value,
        parent_id=am_id,
        district_id=district.id,
        tenant_id=tenant_id,
    )
    po.upazilas = [upazila]
    session.add(po)

    po_other = await hierarchy_user(
        session,
        user_id=po_other_id,
        name="Other PO",
        role=HierarchyRole.PO.value,
        parent_id=am_id,
        district_id=district.id,
        tenant_id=tenant_id,
    )
    po_other.upazilas = [upazila_other]
    session.add(po_other)
    await session.flush()

    sk = await hierarchy_user(
        session,
        user_id=sk_id,
        name="Test Shastiya Kormi",
        role=HierarchyRole.SHASTIYA_KORMI.value,
        parent_id=po_id,
        district_id=district.id,
        tenant_id=tenant_id,
    )
    sk.upazilas = [upazila]
    session.add(sk)

    sk_other = await hierarchy_user(
        session,
        user_id=sk_other_id,
        name="Other Shastiya Kormi",
        role=HierarchyRole.SHASTIYA_KORMI.value,
        parent_id=po_other_id,
        district_id=district.id,
        tenant_id=tenant_id,
    )
    sk_other.upazilas = [upazila_other]
    session.add(sk_other)
    await session.flush()

    return HierarchySeed(
        tenant_id=tenant_id,
        division_id=division.id,
        division_name=division_name,
        district_id=district.id,
        upazila_id=upazila.id,
        upazila_other_id=upazila_other.id,
        upazila_name=upazila_name,
        upazila_other_name=upazila_other_name,
        district_name=district_name,
        am_id=am_id,
        po_id=po_id,
        po_other_id=po_other_id,
        sk_id=sk_id,
        sk_other_id=sk_other_id,
    )


@dataclass(frozen=True, slots=True)
class MultiDistrictHierarchySeed:
    tenant_id: int
    division_id: int
    primary: HierarchySeed
    secondary_district_id: int
    secondary_po_id: int


async def seed_multi_district_hierarchy(
    session: AsyncSession,
    *,
    tenant_id: int = DEFAULT_TENANT_ID,
    secondary_district_name: str = "Nilphamari",
    secondary_upazila_name: str = "Nilphamari Sadar",
    secondary_po_id: int = 2100,
    secondary_sk_id: int = 3100,
) -> MultiDistrictHierarchySeed:
    """Two districts under one division; secondary district has one PO and one SK."""
    primary = await seed_basic_hierarchy(session, tenant_id=tenant_id)

    secondary_district = District(
        name=secondary_district_name,
        division_id=primary.division_id,
        tenant_id=tenant_id,
        created_by=None,
        updated_by=None,
    )
    session.add(secondary_district)
    await session.flush()

    secondary_upazila = Upazila(
        name=secondary_upazila_name,
        district_id=secondary_district.id,
        tenant_id=tenant_id,
        created_by=None,
        updated_by=None,
    )
    session.add(secondary_upazila)
    await session.flush()

    secondary_po = await hierarchy_user(
        session,
        user_id=secondary_po_id,
        name="Secondary PO",
        role=HierarchyRole.PO.value,
        parent_id=primary.am_id,
        district_id=secondary_district.id,
        tenant_id=tenant_id,
    )
    secondary_po.upazilas = [secondary_upazila]
    session.add(secondary_po)
    await session.flush()

    secondary_sk = await hierarchy_user(
        session,
        user_id=secondary_sk_id,
        name="Secondary SK",
        role=HierarchyRole.SHASTIYA_KORMI.value,
        parent_id=secondary_po_id,
        district_id=secondary_district.id,
        tenant_id=tenant_id,
    )
    secondary_sk.upazilas = [secondary_upazila]
    session.add(secondary_sk)
    await session.flush()

    return MultiDistrictHierarchySeed(
        tenant_id=tenant_id,
        division_id=primary.division_id,
        primary=primary,
        secondary_district_id=secondary_district.id,
        secondary_po_id=secondary_po_id,
    )


HIERARCHY_TRUNCATE_SQL = (
    'TRUNCATE "users", district, upazila, user_upazila, division RESTART IDENTITY CASCADE'
)
