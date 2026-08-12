"""Tests for GET /dashboard/published-module-completions (no PostgreSQL required)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_contracts.dashboard import (
    PublishedModuleCompletionItem,
    PublishedModuleCompletionsResponse,
)
from mc_contracts.enums import HierarchyRole
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import register_problem_handlers
from platform_service.api.dashboard import router as dashboard_router
from platform_service.auth.spice_context import SpiceUserContext
from platform_service.auth.spice_identity import PublishedModuleCompletionsScope
from platform_service.config import get_settings
from platform_service.deps import get_db
from platform_service.services.dashboard_hierarchy import OrgUser

from tests.conftest import platform_path

pytestmark = pytest.mark.asyncio

AM_ID = 100
PO_ID = 401
ADMIN_ID = 999
TEST_TENANT_ID = 7


def _org_user(
    user_id: int,
    *,
    role: str,
    parent_id: int | None = None,
    name: str | None = None,
) -> OrgUser:
    return OrgUser(
        id=user_id,
        name=name or f"user-{user_id}",
        role=role,
        district_id=1,
        district=None,
        upazila_ids=frozenset(),
        upazila_names=frozenset(),
        parent_id=parent_id,
    )


@pytest_asyncio.fixture
async def app(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    auth_on = get_settings().model_copy(update={"spice_auth_enabled": True})
    monkeypatch.setattr("platform_service.auth.spice_identity.get_settings", lambda: auth_on)
    monkeypatch.setattr("platform_service.auth.spice_user.get_settings", lambda: auth_on)
    monkeypatch.setattr(
        "platform_service.auth.spice_identity.org_user_index",
        AsyncMock(return_value={}),
    )

    app_obj = FastAPI()
    register_problem_handlers(
        app_obj,
        validation_error_type=RequestValidationError,
        http_exception_type=HTTPException,
    )

    @app_obj.middleware("http")
    async def inject_spice_user(request: Request, call_next):  # type: ignore[no-untyped-def]
        role = request.headers.get("X-Test-Role", "head office")
        user_id = int(request.headers.get("X-Test-User-Id", str(ADMIN_ID)))
        suite = request.headers.get("X-Test-Suite", "admin")
        request.state.spice_user = SpiceUserContext.model_validate(
            {
                "id": user_id,
                "username": "test_user",
                "tenantId": TEST_TENANT_ID,
                "organizationIds": [TEST_TENANT_ID],
                "roles": [{"name": role, "suiteAccessName": suite}],
            }
        )
        request.state.selected_tenant_id = TEST_TENANT_ID
        return await call_next(request)

    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(dashboard_router)
    app_obj.include_router(api_router)

    session_mock = MagicMock()
    app_obj.dependency_overrides[get_db] = lambda: session_mock

    module_id = uuid4()
    family_id = uuid4()
    service_mock = AsyncMock(
        return_value=PublishedModuleCompletionsResponse(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            total_modules=1,
            total_descendant_sk_count=5,
            limit=20,
            offset=0,
            modules=[
                PublishedModuleCompletionItem(
                    module_id=module_id,
                    module_family_id=family_id,
                    title={"en": "M1"},
                    published_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
                    completed_sk_count=2,
                    total_descendant_sk_count=5,
                )
            ],
        )
    )
    monkeypatch.setattr(
        "platform_service.services.published_module_completions_service"
        ".PublishedModuleCompletionsService.get_published_module_completions",
        service_mock,
    )
    app_obj.state.service_mock = service_mock

    yield app_obj
    app_obj.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestPublishedModuleCompletionsRoute:
    async def test_admin_unrestricted(self, client: AsyncClient, app: FastAPI) -> None:
        resp = await client.get(
            platform_path("/dashboard/published-module-completions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={
                "X-Test-Role": "head office",
                "X-Test-User-Id": str(ADMIN_ID),
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_modules"] == 1
        assert data["total_descendant_sk_count"] == 5
        assert data["modules"][0]["completed_sk_count"] == 2
        assert data["modules"][0]["title"] == {"en": "M1"}
        scope = app.state.service_mock.await_args.kwargs["scope"]
        assert scope == PublishedModuleCompletionsScope(viewer_id=ADMIN_ID, unrestricted=True)

    async def test_area_manager_scoped(
        self, client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "platform_service.auth.spice_identity.org_user_index",
            AsyncMock(
                return_value={
                    AM_ID: _org_user(AM_ID, role=HierarchyRole.AREA_MANAGER.value, name="AM"),
                }
            ),
        )
        resp = await client.get(
            platform_path("/dashboard/published-module-completions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={
                "X-Test-Role": "AREA_MANAGER",
                "X-Test-User-Id": str(AM_ID),
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 200
        scope = app.state.service_mock.await_args.kwargs["scope"]
        assert scope == PublishedModuleCompletionsScope(viewer_id=AM_ID, unrestricted=False)

    async def test_po_organizer_forbidden(self, client: AsyncClient) -> None:
        resp = await client.get(
            platform_path("/dashboard/published-module-completions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={
                "X-Test-Role": "PO",
                "X-Test-User-Id": str(PO_ID),
                "X-Test-Suite": "mob",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == ErrorCode.FORBIDDEN.value

    async def test_sk_device_forbidden(self, client: AsyncClient) -> None:
        resp = await client.get(
            platform_path("/dashboard/published-module-completions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={
                "X-Test-Role": "SHASTIYA_KORMI",
                "X-Test-User-Id": "395",
                "X-Test-Suite": "mob",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == ErrorCode.FORBIDDEN.value

    async def test_invalid_date_range_returns_422(self, client: AsyncClient) -> None:
        resp = await client.get(
            platform_path("/dashboard/published-module-completions"),
            params={"from_date": "2026-02-01", "to_date": "2026-01-01"},
            headers={
                "X-Test-Role": "head office",
                "X-Test-User-Id": str(ADMIN_ID),
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 422

    async def test_auth_off_unrestricted(
        self, client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        auth_off = get_settings().model_copy(update={"spice_auth_enabled": False})
        monkeypatch.setattr("platform_service.auth.spice_identity.get_settings", lambda: auth_off)
        resp = await client.get(
            platform_path("/dashboard/published-module-completions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31", "limit": 10, "offset": 5},
        )
        assert resp.status_code == 200
        kwargs = app.state.service_mock.await_args.kwargs
        assert kwargs["scope"] == PublishedModuleCompletionsScope(viewer_id=None, unrestricted=True)
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 5
