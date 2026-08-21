"""Role catalog + users.role_id FK / hierarchy trigger coverage."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from platform_service.db.models.district import District
from platform_service.db.models.hierarchy_user import HierarchyUser
from platform_service.db.models.role import Role
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.helpers.hierarchy_fixtures import (
    AM_ID,
    PO_ID,
    ensure_hierarchy_roles,
    hierarchy_user,
    seed_basic_hierarchy,
)

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _wipe_hierarchy(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text('TRUNCATE "users", district, upazila, user_upazila, division RESTART IDENTITY CASCADE')
    )
    await db_session.commit()


async def test_role_catalog_seeded_with_three_codes(db_session: AsyncSession) -> None:
    roles = await ensure_hierarchy_roles(db_session)
    codes = set(roles)
    assert codes == {"AREA_MANAGER", "PO", "SHASTIYA_KORMI"}
    rows = (await db_session.execute(select(Role))).scalars().all()
    assert {r.code for r in rows} >= codes


async def test_invalid_role_id_rejected(db_session: AsyncSession) -> None:
    """Missing role_id is rejected by FK and/or the hierarchy trigger."""
    district = District(
        name="FK District",
        tenant_id=0,
        created_by=None,
        updated_by=None,
    )
    db_session.add(district)
    await db_session.flush()

    db_session.add(
        HierarchyUser(
            id=9001,
            name="Bad Role User",
            role_id=9_999_999,
            parent_id=None,
            district_id=district.id,
            tenant_id=0,
            created_by=None,
            updated_by=None,
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await db_session.flush()


async def test_hierarchy_trigger_rejects_wrong_parent_role(db_session: AsyncSession) -> None:
    seed = await seed_basic_hierarchy(db_session, tenant_id=0)
    await db_session.commit()

    # SK must parent under PO, not under AM.
    bad_sk = await hierarchy_user(
        db_session,
        user_id=9100,
        name="Bad SK",
        role="SHASTIYA_KORMI",
        parent_id=AM_ID,
        district_id=seed.district_id,
        tenant_id=0,
    )
    db_session.add(bad_sk)
    with pytest.raises((IntegrityError, DBAPIError)):
        await db_session.flush()
    await db_session.rollback()

    # Valid SK under PO still works (seed survived the rollback above).
    good_sk = await hierarchy_user(
        db_session,
        user_id=9101,
        name="Good SK",
        role="SHASTIYA_KORMI",
        parent_id=PO_ID,
        district_id=seed.district_id,
        tenant_id=0,
    )
    db_session.add(good_sk)
    await db_session.flush()
    loaded = await db_session.get(HierarchyUser, 9101)
    assert loaded is not None
    assert loaded.role == "SHASTIYA_KORMI"
