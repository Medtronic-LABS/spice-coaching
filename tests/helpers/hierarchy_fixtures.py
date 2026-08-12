"""Shared hierarchy seed helpers for tests that need AM → PO → SK trees."""

from __future__ import annotations

from dataclasses import dataclass

from mc_contracts.enums import HierarchyRole
from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.district import District
from platform_service.db.models.hierarchy_user import HierarchyUser
from platform_service.db.models.upazila import Upazila
from sqlalchemy.ext.asyncio import AsyncSession

# Stable IDs used across assignment / sync / demand / document-usage tests.
AM_ID = 1001
PO_ID = 2001
PO_OTHER_ID = 2002
SK_ID = 3001
SK_OTHER_ID = 3002


@dataclass(frozen=True, slots=True)
class HierarchySeed:
    tenant_id: int
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
    district_name: str = "Lalmonirhat",
    upazila_name: str = "Lalmonirhat Sadar",
    upazila_other_name: str = "Aditmari",
    am_id: int = AM_ID,
    po_id: int = PO_ID,
    po_other_id: int = PO_OTHER_ID,
    sk_id: int = SK_ID,
    sk_other_id: int = SK_OTHER_ID,
) -> HierarchySeed:
    """Insert district + upazilas + AM → two POs → two SKs (one under each PO)."""
    district = District(
        name=district_name,
        tenant_id=tenant_id,
        created_by="test",
        updated_by="test",
    )
    session.add(district)
    await session.flush()

    upazila = Upazila(
        name=upazila_name,
        district_id=district.id,
        tenant_id=tenant_id,
        created_by="test",
        updated_by="test",
    )
    upazila_other = Upazila(
        name=upazila_other_name,
        district_id=district.id,
        tenant_id=tenant_id,
        created_by="test",
        updated_by="test",
    )
    session.add(upazila)
    session.add(upazila_other)
    await session.flush()

    am = HierarchyUser(
        id=am_id,
        name="Test Area Manager",
        role=HierarchyRole.AREA_MANAGER.value,
        parent_id=None,
        district_id=district.id,
        tenant_id=tenant_id,
        created_by="test",
        updated_by="test",
    )
    am.upazilas = []
    session.add(am)
    await session.flush()

    po = HierarchyUser(
        id=po_id,
        name="Test PO",
        role=HierarchyRole.PO.value,
        parent_id=am_id,
        district_id=district.id,
        tenant_id=tenant_id,
        created_by="test",
        updated_by="test",
    )
    po.upazilas = [upazila]
    session.add(po)

    po_other = HierarchyUser(
        id=po_other_id,
        name="Other PO",
        role=HierarchyRole.PO.value,
        parent_id=am_id,
        district_id=district.id,
        tenant_id=tenant_id,
        created_by="test",
        updated_by="test",
    )
    po_other.upazilas = [upazila_other]
    session.add(po_other)
    await session.flush()

    sk = HierarchyUser(
        id=sk_id,
        name="Test Shastiya Kormi",
        role=HierarchyRole.SHASTIYA_KORMI.value,
        parent_id=po_id,
        district_id=district.id,
        tenant_id=tenant_id,
        created_by="test",
        updated_by="test",
    )
    sk.upazilas = [upazila]
    session.add(sk)

    sk_other = HierarchyUser(
        id=sk_other_id,
        name="Other Shastiya Kormi",
        role=HierarchyRole.SHASTIYA_KORMI.value,
        parent_id=po_other_id,
        district_id=district.id,
        tenant_id=tenant_id,
        created_by="test",
        updated_by="test",
    )
    sk_other.upazilas = [upazila_other]
    session.add(sk_other)
    await session.flush()

    return HierarchySeed(
        tenant_id=tenant_id,
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


HIERARCHY_TRUNCATE_SQL = 'TRUNCATE "users", district, upazila, user_upazila RESTART IDENTITY CASCADE'
