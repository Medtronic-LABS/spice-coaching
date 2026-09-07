"""Unit/integration tests for hierarchy-backed document-usage scoping."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from mc_contracts.enums import HierarchyRole
from platform_service.db.models.hierarchy_user import ROLE_SUPER_ADMIN
from platform_service.db.repositories.hierarchy_repository import HierarchyRepository
from platform_service.services.document_usage_hierarchy import (
    OrgUser,
    apply_document_usage_filters,
    filter_users_by_chw_ids,
    org_user_index,
    resolve_users_by_geography_ids,
    resolve_users_by_geography_names,
    resolve_visible_chw_ids,
    user_display,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.helpers.hierarchy_fixtures import (
    AM_ID,
    PO_ID,
    PO_OTHER_ID,
    SK_ID,
    SK_OTHER_ID,
    seed_basic_hierarchy,
)

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _wipe_and_seed(db_session: AsyncSession) -> AsyncIterator[None]:
    await db_session.execute(
        text('TRUNCATE "users", district, upazila, user_upazila, division RESTART IDENTITY CASCADE')
    )
    await db_session.commit()
    await seed_basic_hierarchy(db_session)
    await db_session.commit()
    yield
    await db_session.rollback()
    await db_session.execute(
        text('TRUNCATE "users", district, upazila, user_upazila, division RESTART IDENTITY CASCADE')
    )
    await db_session.commit()


class TestResolveVisibleChwIds:
    async def test_unrestricted_returns_none(self, db_session: AsyncSession) -> None:
        assert await resolve_visible_chw_ids(db_session, None, tenant_id=0, unrestricted=True) is None
        assert await resolve_visible_chw_ids(db_session, 401, tenant_id=0, unrestricted=True) is None

    async def test_pm_sees_self_and_sks(self, db_session: AsyncSession) -> None:
        visible = await resolve_visible_chw_ids(db_session, PO_ID, tenant_id=0)
        assert visible is not None
        assert PO_ID in visible
        index = await org_user_index(db_session, tenant_id=0)
        for uid in visible:
            user = index[uid]
            assert user.id == PO_ID or (
                user.role == HierarchyRole.SHASTIYA_KORMI.value and user.parent_id == PO_ID
            )

    async def test_am_sees_descendant_pms_and_sks(self, db_session: AsyncSession) -> None:
        visible = await resolve_visible_chw_ids(db_session, AM_ID, tenant_id=0)
        assert visible is not None
        assert AM_ID in visible
        index = await org_user_index(db_session, tenant_id=0)
        pm_ids = {u.id for u in index.values() if u.role == HierarchyRole.PO.value and u.parent_id == AM_ID}
        assert pm_ids
        assert pm_ids.issubset(visible)
        for uid in visible:
            user = index[uid]
            assert user.id == AM_ID or user.role in {
                HierarchyRole.PO.value,
                HierarchyRole.SHASTIYA_KORMI.value,
            }

    async def test_missing_viewer_id_without_unrestricted_is_empty(self, db_session: AsyncSession) -> None:
        assert await resolve_visible_chw_ids(db_session, None, tenant_id=0, unrestricted=False) == frozenset()

    async def test_unknown_viewer_id_treated_as_unrestricted(self, db_session: AsyncSession) -> None:
        assert (
            await resolve_visible_chw_ids(db_session, 9_999_999_999, tenant_id=0, unrestricted=False) is None
        )

    async def test_am_exclude_self_sees_only_descendants(self, db_session: AsyncSession) -> None:
        visible = await resolve_visible_chw_ids(
            db_session,
            AM_ID,
            tenant_id=0,
            include_self=False,
        )
        assert visible is not None
        assert AM_ID not in visible
        index = await org_user_index(db_session, tenant_id=0)
        po_ids = {u.id for u in index.values() if u.role == HierarchyRole.PO.value and u.parent_id == AM_ID}
        assert po_ids
        assert po_ids.issubset(visible)
        for uid in visible:
            user = index[uid]
            assert user.role in {
                HierarchyRole.PO.value,
                HierarchyRole.SHASTIYA_KORMI.value,
            }

    async def test_po_exclude_self_sees_only_sk_children(self, db_session: AsyncSession) -> None:
        visible = await resolve_visible_chw_ids(
            db_session,
            PO_ID,
            tenant_id=0,
            include_self=False,
        )
        assert visible == frozenset({SK_ID})

    async def test_sk_include_self_false_still_self_only(self, db_session: AsyncSession) -> None:
        visible = await resolve_visible_chw_ids(
            db_session,
            SK_ID,
            tenant_id=0,
            include_self=False,
        )
        assert visible == frozenset({SK_ID})


class TestOrgUserIndexSuperAdmin:
    SUPER_ADMIN_ID = 9001

    async def test_super_admin_has_null_district(self, db_session: AsyncSession) -> None:
        await HierarchyRepository(db_session).ensure_super_admin_user(
            user_id=self.SUPER_ADMIN_ID,
            name="Admin",
            tenant_id=0,
        )
        await db_session.commit()

        index = await org_user_index(db_session, tenant_id=0)
        admin = index[self.SUPER_ADMIN_ID]
        assert admin.role == ROLE_SUPER_ADMIN
        assert admin.district_id is None
        assert admin.district is None
        assert admin.upazila_ids == frozenset()


class TestApplyDocumentUsageFilters:
    async def test_po_focus_outside_visible_is_empty(self, db_session: AsyncSession) -> None:
        visible = await resolve_visible_chw_ids(db_session, PO_ID, tenant_id=0)
        assert visible is not None
        narrowed = await apply_document_usage_filters(
            db_session,
            visible,
            tenant_id=0,
            user_id=PO_OTHER_ID,
        )
        assert narrowed is not None
        assert len(narrowed) == 0

    async def test_sk_focus_within_po_tree(self, db_session: AsyncSession) -> None:
        visible = await resolve_visible_chw_ids(db_session, PO_ID, tenant_id=0)
        result = await apply_document_usage_filters(
            db_session,
            visible,
            tenant_id=0,
            user_id=SK_ID,
        )
        assert result == frozenset({SK_ID})

    async def test_po_focus_includes_self_and_sks(self, db_session: AsyncSession) -> None:
        result = await apply_document_usage_filters(
            db_session,
            None,
            tenant_id=0,
            user_id=PO_ID,
        )
        assert result is not None
        assert PO_ID in result
        assert SK_ID in result

    async def test_district_filter_from_unrestricted(self, db_session: AsyncSession) -> None:
        index = await org_user_index(db_session, tenant_id=0)
        district_id = next(user.district_id for user in index.values() if user.district == "Lalmonirhat")
        result = await apply_document_usage_filters(
            db_session,
            None,
            tenant_id=0,
            district_ids=[district_id],
        )
        assert result is not None
        assert len(result) > 0
        assert all(index[uid].district_id == district_id for uid in result)

    async def test_division_filter_from_unrestricted(self, db_session: AsyncSession) -> None:
        index = await org_user_index(db_session, tenant_id=0)
        division_id = next(
            user.division_id
            for user in index.values()
            if user.division == "Rangpur" and user.division_id is not None
        )
        result = await apply_document_usage_filters(
            db_session,
            None,
            tenant_id=0,
            division_ids=[division_id],
        )
        assert result is not None
        assert len(result) > 0
        assert all(index[uid].division_id == division_id for uid in result)

    async def test_upazila_filter_from_unrestricted(self, db_session: AsyncSession) -> None:
        index = await org_user_index(db_session, tenant_id=0)
        upazila_id = next(
            next(iter(user.upazila_ids))
            for user in index.values()
            if "Lalmonirhat Sadar" in user.upazila_names
        )
        result = await apply_document_usage_filters(
            db_session,
            None,
            tenant_id=0,
            upazila_ids=[upazila_id],
        )
        assert result is not None
        assert len(result) > 0
        assert all(upazila_id in index[uid].upazila_ids for uid in result)

    async def test_filter_users_by_chw_ids_none_passthrough(self) -> None:
        users = [
            OrgUser(
                id=1,
                name="A",
                role="PO",
                district_id=1,
                district="Lalmonirhat",
                division_id=1,
                division="Rangpur",
                upazila_ids=frozenset({1}),
                upazila_names=frozenset({"Lalmonirhat Sadar"}),
                parent_id=None,
            )
        ]
        assert filter_users_by_chw_ids(users, None) == users

    async def test_filter_users_by_chw_ids_intersects(self) -> None:
        users = [
            OrgUser(
                id=1,
                name="A",
                role="PO",
                district_id=1,
                district="Lalmonirhat",
                division_id=1,
                division="Rangpur",
                upazila_ids=frozenset({1}),
                upazila_names=frozenset({"Lalmonirhat Sadar"}),
                parent_id=None,
            ),
            OrgUser(
                id=2,
                name="B",
                role="SHASTIYA_KORMI",
                district_id=1,
                district="Lalmonirhat",
                division_id=1,
                division="Rangpur",
                upazila_ids=frozenset({2}),
                upazila_names=frozenset({"Aditmari"}),
                parent_id=1,
            ),
        ]
        filtered = filter_users_by_chw_ids(users, frozenset({2}))
        assert [u.id for u in filtered] == [2]

    async def test_user_display_known_and_unknown(self, db_session: AsyncSession) -> None:
        index = await org_user_index(db_session, tenant_id=0)
        display = user_display(PO_ID, index)
        assert display["user_name"]
        assert display["user_role"] == HierarchyRole.PO.value
        unknown = user_display(9_999_999_999, index)
        assert unknown["user_name"] is None
        assert unknown["user_role"] is None


class TestResolveUsersByGeographyNames:
    async def test_returns_none_when_all_unset(self, db_session: AsyncSession) -> None:
        assert await resolve_users_by_geography_names(db_session, tenant_id=0) is None

    async def test_single_division_filter(self, db_session: AsyncSession) -> None:
        result = await resolve_users_by_geography_names(
            db_session,
            tenant_id=0,
            divisions=["Rangpur"],
        )
        assert result is not None
        index = await org_user_index(db_session, tenant_id=0)
        assert all(index[uid].division == "Rangpur" for uid in result)

    async def test_multi_division_or_within_dimension(self, db_session: AsyncSession) -> None:
        result = await resolve_users_by_geography_names(
            db_session,
            tenant_id=0,
            upazilas=["Lalmonirhat Sadar", "Aditmari"],
        )
        assert result is not None
        assert SK_ID in result
        assert SK_OTHER_ID in result
        assert AM_ID not in result

    async def test_and_across_division_district_upazila(self, db_session: AsyncSession) -> None:
        result = await resolve_users_by_geography_names(
            db_session,
            tenant_id=0,
            divisions=["Rangpur"],
            districts=["Lalmonirhat"],
            upazilas=["Aditmari"],
        )
        assert result == frozenset({SK_OTHER_ID})

    async def test_unknown_name_returns_empty_set(self, db_session: AsyncSession) -> None:
        result = await resolve_users_by_geography_names(
            db_session,
            tenant_id=0,
            divisions=["Unknown"],
        )
        assert result == frozenset()


class TestResolveUsersByGeographyIds:
    async def test_returns_none_when_all_unset(self, db_session: AsyncSession) -> None:
        assert await resolve_users_by_geography_ids(db_session, tenant_id=0) is None

    async def test_single_division_id_filter(self, db_session: AsyncSession) -> None:
        index = await org_user_index(db_session, tenant_id=0)
        division_id = next(u.division_id for u in index.values() if u.division_id is not None)
        result = await resolve_users_by_geography_ids(
            db_session,
            tenant_id=0,
            division_ids=[division_id],
            index=index,
        )
        assert result is not None
        assert all(index[uid].division_id == division_id for uid in result)

    async def test_multi_upazila_id_or_within_dimension(self, db_session: AsyncSession) -> None:
        index = await org_user_index(db_session, tenant_id=0)
        upazila_ids = sorted({next(iter(user.upazila_ids)) for user in index.values() if user.upazila_ids})
        result = await resolve_users_by_geography_ids(
            db_session,
            tenant_id=0,
            upazila_ids=upazila_ids,
            index=index,
        )
        assert result is not None
        assert SK_ID in result
        assert SK_OTHER_ID in result
        assert AM_ID not in result

    async def test_and_across_division_district_upazila_ids(self, db_session: AsyncSession) -> None:
        index = await org_user_index(db_session, tenant_id=0)
        sk_other = index[SK_OTHER_ID]
        upazila_id = next(iter(sk_other.upazila_ids))
        assert sk_other.division_id is not None
        result = await resolve_users_by_geography_ids(
            db_session,
            tenant_id=0,
            division_ids=[sk_other.division_id],
            district_ids=[sk_other.district_id],
            upazila_ids=[upazila_id],
            index=index,
        )
        assert result == frozenset({SK_OTHER_ID})

    async def test_unknown_id_returns_empty_set(self, db_session: AsyncSession) -> None:
        result = await resolve_users_by_geography_ids(
            db_session,
            tenant_id=0,
            division_ids=[999_999],
        )
        assert result == frozenset()
