"""Unit/integration tests for hierarchy-backed document-usage scoping."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from mc_contracts.enums import HierarchyRole
from platform_service.services.document_usage_hierarchy import (
    apply_document_usage_filters,
    org_user_index,
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
    seed_basic_hierarchy,
)

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _wipe_and_seed(db_session: AsyncSession) -> AsyncIterator[None]:
    await db_session.execute(
        text('TRUNCATE "users", district, upazila, user_upazila RESTART IDENTITY CASCADE')
    )
    await db_session.commit()
    await seed_basic_hierarchy(db_session)
    await db_session.commit()
    yield
    await db_session.rollback()
    await db_session.execute(
        text('TRUNCATE "users", district, upazila, user_upazila RESTART IDENTITY CASCADE')
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
        result = await apply_document_usage_filters(
            db_session,
            None,
            tenant_id=0,
            district="Lalmonirhat",
        )
        assert result is not None
        assert len(result) > 0
        index = await org_user_index(db_session, tenant_id=0)
        assert all(index[uid].district == "Lalmonirhat" for uid in result)

    async def test_upazila_filter_from_unrestricted(self, db_session: AsyncSession) -> None:
        result = await apply_document_usage_filters(
            db_session,
            None,
            tenant_id=0,
            upazila="Lalmonirhat Sadar",
        )
        assert result is not None
        assert len(result) > 0
        index = await org_user_index(db_session, tenant_id=0)
        assert all("Lalmonirhat Sadar" in index[uid].upazila_names for uid in result)

    async def test_user_display_known_and_unknown(self, db_session: AsyncSession) -> None:
        index = await org_user_index(db_session, tenant_id=0)
        display = user_display(PO_ID, index)
        assert display["user_name"]
        assert display["user_role"] == HierarchyRole.PO.value
        unknown = user_display(9_999_999_999, index)
        assert unknown["user_name"] is None
        assert unknown["user_role"] is None
