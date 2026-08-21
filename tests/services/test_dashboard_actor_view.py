"""Unit tests for dashboard PO/SK actor-view filtering."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mc_contracts.enums import DashboardActorView, HierarchyRole
from platform_service.api.dashboard import _apply_optional_actor_view
from platform_service.services.dashboard_hierarchy import (
    OrgUser,
    actor_view_role,
    filter_chw_ids_by_role,
)
from starlette.requests import Request

pytestmark = pytest.mark.asyncio

AM_ID = 100
PO_ID = 401
SK_ID = 395
ADMIN_ID = 999
TEST_TENANT_ID = 7


def _org_user(
    user_id: int,
    *,
    role: str,
    parent_id: int | None = None,
) -> OrgUser:
    return OrgUser(
        id=user_id,
        name=f"user-{user_id}",
        role=role,
        district_id=1,
        district=None,
        division_id=None,
        division=None,
        upazila_ids=frozenset(),
        upazila_names=frozenset(),
        parent_id=parent_id,
    )


def _org_index() -> dict[int, OrgUser]:
    return {
        AM_ID: _org_user(AM_ID, role=HierarchyRole.AREA_MANAGER.value),
        PO_ID: _org_user(PO_ID, role=HierarchyRole.PO.value, parent_id=AM_ID),
        SK_ID: _org_user(SK_ID, role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=PO_ID),
        ADMIN_ID: _org_user(ADMIN_ID, role=HierarchyRole.SUPER_ADMIN.value),
    }


class TestActorViewRole:
    def test_maps_po_and_sk(self) -> None:
        assert actor_view_role(DashboardActorView.PO) == HierarchyRole.PO.value
        assert actor_view_role(DashboardActorView.SK) == HierarchyRole.SHASTIYA_KORMI.value


class TestFilterChwIdsByRole:
    @patch(
        "platform_service.services.dashboard_hierarchy.org_user_index",
        new_callable=AsyncMock,
    )
    async def test_unrestricted_materializes_role_ids(self, mock_index: AsyncMock) -> None:
        mock_index.return_value = _org_index()
        session = MagicMock()
        result = await filter_chw_ids_by_role(
            session,
            tenant_id=TEST_TENANT_ID,
            chw_ids=None,
            role=HierarchyRole.PO.value,
        )
        assert result == frozenset({PO_ID})

    @patch(
        "platform_service.services.dashboard_hierarchy.org_user_index",
        new_callable=AsyncMock,
    )
    async def test_intersects_existing_scope(self, mock_index: AsyncMock) -> None:
        mock_index.return_value = _org_index()
        session = MagicMock()
        result = await filter_chw_ids_by_role(
            session,
            tenant_id=TEST_TENANT_ID,
            chw_ids=frozenset({PO_ID, SK_ID, 9999}),
            role=HierarchyRole.SHASTIYA_KORMI.value,
        )
        assert result == frozenset({SK_ID})

    @patch(
        "platform_service.services.dashboard_hierarchy.org_user_index",
        new_callable=AsyncMock,
    )
    async def test_empty_when_no_matching_role(self, mock_index: AsyncMock) -> None:
        mock_index.return_value = _org_index()
        session = MagicMock()
        result = await filter_chw_ids_by_role(
            session,
            tenant_id=TEST_TENANT_ID,
            chw_ids=frozenset({SK_ID}),
            role=HierarchyRole.PO.value,
        )
        assert result == frozenset()


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    return Request(scope)


class TestApplyOptionalActorView:
    async def test_none_view_returns_unchanged(self) -> None:
        chw_ids = frozenset({PO_ID, SK_ID})
        result = await _apply_optional_actor_view(
            _request(),
            MagicMock(),
            chw_ids,
            None,
        )
        assert result == chw_ids

    async def test_auth_off_ignores_view(self) -> None:
        auth_off = MagicMock(spice_auth_enabled=False)
        with patch("platform_service.api.dashboard.get_settings", return_value=auth_off):
            result = await _apply_optional_actor_view(
                _request(),
                MagicMock(),
                frozenset({PO_ID, SK_ID}),
                DashboardActorView.PO,
            )
        assert result == frozenset({PO_ID, SK_ID})

    @patch("platform_service.api.dashboard.get_selected_tenant_id", return_value=TEST_TENANT_ID)
    @patch(
        "platform_service.api.dashboard._dashboard_hierarchy_viewer",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.org_user_index",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.filter_chw_ids_by_role",
        new_callable=AsyncMock,
    )
    async def test_area_manager_honors_view(
        self,
        mock_filter: AsyncMock,
        mock_index: AsyncMock,
        mock_viewer: AsyncMock,
        _tenant: MagicMock,
    ) -> None:
        auth_on = MagicMock(spice_auth_enabled=True)
        mock_viewer.return_value = (AM_ID, False)
        mock_index.return_value = _org_index()
        mock_filter.return_value = frozenset({PO_ID})
        with patch("platform_service.api.dashboard.get_settings", return_value=auth_on):
            result = await _apply_optional_actor_view(
                _request(),
                MagicMock(),
                frozenset({PO_ID, SK_ID}),
                DashboardActorView.PO,
            )
        assert result == frozenset({PO_ID})
        mock_filter.assert_awaited_once()
        assert mock_filter.await_args.kwargs["role"] == HierarchyRole.PO.value

    @patch("platform_service.api.dashboard.get_selected_tenant_id", return_value=TEST_TENANT_ID)
    @patch(
        "platform_service.api.dashboard._dashboard_hierarchy_viewer",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.org_user_index",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.filter_chw_ids_by_role",
        new_callable=AsyncMock,
    )
    async def test_po_ignores_view(
        self,
        mock_filter: AsyncMock,
        mock_index: AsyncMock,
        mock_viewer: AsyncMock,
        _tenant: MagicMock,
    ) -> None:
        auth_on = MagicMock(spice_auth_enabled=True)
        mock_viewer.return_value = (PO_ID, False)
        mock_index.return_value = _org_index()
        visible = frozenset({SK_ID})
        with patch("platform_service.api.dashboard.get_settings", return_value=auth_on):
            result = await _apply_optional_actor_view(
                _request(),
                MagicMock(),
                visible,
                DashboardActorView.PO,
            )
        assert result == visible
        mock_filter.assert_not_awaited()

    @patch("platform_service.api.dashboard.get_selected_tenant_id", return_value=TEST_TENANT_ID)
    @patch(
        "platform_service.api.dashboard._dashboard_hierarchy_viewer",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.org_user_index",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.filter_chw_ids_by_role",
        new_callable=AsyncMock,
    )
    async def test_super_admin_honors_view(
        self,
        mock_filter: AsyncMock,
        mock_index: AsyncMock,
        mock_viewer: AsyncMock,
        _tenant: MagicMock,
    ) -> None:
        auth_on = MagicMock(spice_auth_enabled=True)
        mock_viewer.return_value = (ADMIN_ID, True)
        mock_index.return_value = _org_index()
        mock_filter.return_value = frozenset({SK_ID})
        with patch("platform_service.api.dashboard.get_settings", return_value=auth_on):
            result = await _apply_optional_actor_view(
                _request(),
                MagicMock(),
                None,
                DashboardActorView.SK,
            )
        assert result == frozenset({SK_ID})
        assert mock_filter.await_args.kwargs["chw_ids"] is None
        assert mock_filter.await_args.kwargs["role"] == HierarchyRole.SHASTIYA_KORMI.value

    @patch("platform_service.api.dashboard.get_selected_tenant_id", return_value=TEST_TENANT_ID)
    @patch(
        "platform_service.api.dashboard._dashboard_hierarchy_viewer",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.org_user_index",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.filter_chw_ids_by_role",
        new_callable=AsyncMock,
    )
    async def test_platform_admin_not_in_map_honors_view(
        self,
        mock_filter: AsyncMock,
        mock_index: AsyncMock,
        mock_viewer: AsyncMock,
        _tenant: MagicMock,
    ) -> None:
        auth_on = MagicMock(spice_auth_enabled=True)
        platform_admin_id = 42_000
        mock_viewer.return_value = (platform_admin_id, True)
        mock_index.return_value = _org_index()
        mock_filter.return_value = frozenset({PO_ID})
        with patch("platform_service.api.dashboard.get_settings", return_value=auth_on):
            result = await _apply_optional_actor_view(
                _request(),
                MagicMock(),
                None,
                DashboardActorView.PO,
            )
        assert result == frozenset({PO_ID})
        mock_filter.assert_awaited_once()
