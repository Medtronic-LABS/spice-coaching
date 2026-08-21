"""Tests for DB role → path-template authorization."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from platform_service.auth.api_route_catalog import (
    ALL_PATH_TEMPLATES,
    SYNC_PATH_TEMPLATES,
    path_templates_for_role,
)
from platform_service.auth.role_route_authorization_middleware import (
    RoleRouteAuthorizationMiddleware,
)
from platform_service.auth.spice_auth_middleware import SpiceAuthMiddleware
from platform_service.auth.spice_context import SpiceContexts, SpiceUserContext
from platform_service.auth.spice_principal import (
    is_admin_principal,
    is_device_principal,
    is_organizer_principal,
)
from platform_service.auth.tenant_context import HEADER_TENANT_ID
from platform_service.config import Settings, get_settings
from platform_service.db.models.hierarchy_user import (
    ROLE_AREA_MANAGER,
    ROLE_PO,
    ROLE_SHASTIYA_KORMI,
    ROLE_SUPER_ADMIN,
)
from platform_service.integrations.spice_auth_client import SpiceAuthClient
from pydantic_settings import SettingsConfigDict

API_ROOT = "/medtronics-api"
VALID_TOKEN = "Bearer test.jwt.token"
AUTH_HEADERS = {"Authorization": VALID_TOKEN, HEADER_TENANT_ID: "1", "client": "web"}
MOB_AUTH_HEADERS = {"Authorization": VALID_TOKEN, HEADER_TENANT_ID: "1", "client": "mob"}

ROLE_ID_AM = 1
ROLE_ID_PO = 2
ROLE_ID_SK = 3
ROLE_ID_SUPER_ADMIN = 4

AREA_MANAGER = SpiceUserContext.model_validate(
    {
        "id": 10,
        "username": "am_user",
        "country": {"tenantId": 1},
        "roles": [{"name": "AREA_MANAGER", "suiteAccessName": "admin"}],
    }
)
DEVICE_USER = SpiceUserContext.model_validate(
    {
        "id": 2,
        "username": "chw_user",
        "organizationIds": [1],
        "country": {"tenantId": 1},
        "roles": [{"name": "SHASTIYA_KORMI", "suiteAccessName": "mob"}],
    }
)
PO_USER = SpiceUserContext.model_validate(
    {
        "id": 5,
        "username": "po_user",
        "organizationIds": [1],
        "country": {"tenantId": 1},
        "roles": [{"name": "PO", "suiteAccessName": "mob"}],
    }
)
SUPER_ADMIN_USER = SpiceUserContext.model_validate(
    {
        "id": 11,
        "username": "super_admin",
        "isSuperUser": False,
        "country": {"tenantId": 1},
        "roles": [{"name": "SUPER_ADMIN", "suiteAccessName": "admin"}],
    }
)
SUPER_USER = SpiceUserContext.model_validate(
    {
        "id": 3,
        "username": "super",
        "isSuperUser": True,
        "country": {"tenantId": 1},
        "roles": [{"name": "SUPER_USER", "suiteAccessName": "admin"}],
    }
)
JOB_USER = SpiceUserContext.model_validate(
    {
        "id": 4,
        "username": "job",
        "isJobUser": True,
        "organizationIds": [1],
        "country": {"tenantId": 1},
        "roles": [{"name": "JOB_USER", "suiteAccessName": "mob"}],
    }
)

_ROLE_ID_BY_USER_ID = {
    AREA_MANAGER.id: ROLE_ID_AM,
    PO_USER.id: ROLE_ID_PO,
    DEVICE_USER.id: ROLE_ID_SK,
    SUPER_ADMIN_USER.id: ROLE_ID_SUPER_ADMIN,
}

_CODE_BY_ROLE_ID = {
    ROLE_ID_AM: ROLE_AREA_MANAGER,
    ROLE_ID_PO: ROLE_PO,
    ROLE_ID_SK: ROLE_SHASTIYA_KORMI,
    ROLE_ID_SUPER_ADMIN: ROLE_SUPER_ADMIN,
}


def _contexts_for(user: SpiceUserContext) -> SpiceContexts:
    return SpiceContexts(user_detail=user, tenants=None)


class _FakeRoleRouteAccessRepository:
    def __init__(self, _session: Any) -> None:
        pass

    async def list_all_path_templates(self) -> list[str]:
        return list(ALL_PATH_TEMPLATES)

    async def list_path_templates_for_role(self, role_id: int) -> list[str]:
        code = _CODE_BY_ROLE_ID.get(role_id)
        if code is None:
            return []
        return list(path_templates_for_role(code))


@asynccontextmanager
async def _fake_session_local() -> AsyncIterator[MagicMock]:
    yield MagicMock()


async def _fake_enforce_hierarchy(
    _session: Any,
    user: SpiceUserContext,
) -> int | None:
    if user.is_super_user or user.is_job_user:
        return None
    return _ROLE_ID_BY_USER_ID.get(user.id)


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setattr(
        Settings,
        "model_config",
        SettingsConfigDict(env_file=None, env_file_encoding="utf-8", extra="ignore"),
    )
    monkeypatch.setattr(
        "platform_service.auth.spice_auth_middleware.enforce_hierarchy_principal",
        _fake_enforce_hierarchy,
    )
    monkeypatch.setattr(
        "platform_service.auth.role_route_authorization_middleware.SessionLocal",
        _fake_session_local,
    )
    monkeypatch.setattr(
        "platform_service.auth.role_route_authorization_middleware.RoleRouteAccessRepository",
        _FakeRoleRouteAccessRepository,
    )
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def authz_app(mock_spice_client: SpiceAuthClient) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_middleware(RoleRouteAuthorizationMiddleware)
    app.add_middleware(SpiceAuthMiddleware, client=mock_spice_client)

    @app.get(f"{API_ROOT}/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(f"{API_ROOT}/coaching/rag-query")
    async def device_probe() -> dict[str, str]:
        return {"plane": "device"}

    @app.get(f"{API_ROOT}/admin/modules")
    async def admin_probe() -> dict[str, str]:
        return {"plane": "admin"}

    @app.get(f"{API_ROOT}/dashboard/team-activity")
    async def dashboard_probe() -> dict[str, str]:
        return {"plane": "dashboard"}

    @app.get(f"{API_ROOT}/sync/config")
    async def sync_probe() -> dict[str, str]:
        return {"plane": "sync"}

    @app.get(f"{API_ROOT}/admin/unknown-route")
    async def uncatalogued() -> dict[str, str]:
        return {"plane": "missing"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_spice_client() -> SpiceAuthClient:
    client = SpiceAuthClient(base_url="http://auth.test")
    client.authenticate = AsyncMock(return_value=_contexts_for(DEVICE_USER))  # type: ignore[method-assign]
    return client


@pytest_asyncio.fixture
async def authz_client(
    authz_app: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
    monkeypatch.setenv("API_ROOT_PATH", "/medtronics-api")
    get_settings.cache_clear()
    yield authz_app
    get_settings.cache_clear()


def test_is_admin_principal() -> None:
    assert is_admin_principal(AREA_MANAGER) is True
    assert is_admin_principal(DEVICE_USER) is False
    assert is_admin_principal(PO_USER) is False
    assert is_admin_principal(SUPER_USER) is True


def test_is_device_principal() -> None:
    assert is_device_principal(DEVICE_USER) is True
    assert is_device_principal(PO_USER) is True
    assert is_device_principal(AREA_MANAGER) is False
    assert is_device_principal(SUPER_USER) is True
    assert is_device_principal(JOB_USER) is True


def test_is_organizer_principal() -> None:
    assert is_organizer_principal(PO_USER) is True
    assert is_organizer_principal(DEVICE_USER) is False
    assert is_organizer_principal(AREA_MANAGER) is False


def test_super_admin_grants_exclude_sync_router() -> None:
    grants = path_templates_for_role(ROLE_SUPER_ADMIN)
    assert grants == ALL_PATH_TEMPLATES - SYNC_PATH_TEMPLATES
    assert not any(path.startswith("/sync/") for path in grants)
    assert "/coaching/rag-query" in grants
    assert "/morning/cards" in grants
    assert "/telemetry/events" in grants


@pytest.mark.asyncio
async def test_area_manager_reaches_admin_and_dashboard(
    authz_client: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    mock_spice_client.authenticate = AsyncMock(return_value=_contexts_for(AREA_MANAGER))  # type: ignore[method-assign]
    assert (await authz_client.get(f"{API_ROOT}/admin/modules", headers=AUTH_HEADERS)).status_code == 200
    assert (
        await authz_client.get(f"{API_ROOT}/dashboard/team-activity", headers=AUTH_HEADERS)
    ).status_code == 200
    assert (await authz_client.get(f"{API_ROOT}/coaching/rag-query", headers=AUTH_HEADERS)).status_code == 403


@pytest.mark.asyncio
async def test_po_reaches_dashboard_and_device_not_admin(
    authz_client: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    mock_spice_client.authenticate = AsyncMock(return_value=_contexts_for(PO_USER))  # type: ignore[method-assign]
    assert (
        await authz_client.get(f"{API_ROOT}/dashboard/team-activity", headers=MOB_AUTH_HEADERS)
    ).status_code == 200
    assert (
        await authz_client.get(f"{API_ROOT}/coaching/rag-query", headers=MOB_AUTH_HEADERS)
    ).status_code == 200
    assert (await authz_client.get(f"{API_ROOT}/admin/modules", headers=MOB_AUTH_HEADERS)).status_code == 403


@pytest.mark.asyncio
async def test_sk_reaches_device_only(
    authz_client: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    mock_spice_client.authenticate = AsyncMock(return_value=_contexts_for(DEVICE_USER))  # type: ignore[method-assign]
    assert (
        await authz_client.get(f"{API_ROOT}/coaching/rag-query", headers=MOB_AUTH_HEADERS)
    ).status_code == 200
    assert (
        await authz_client.get(f"{API_ROOT}/dashboard/team-activity", headers=MOB_AUTH_HEADERS)
    ).status_code == 403
    assert (await authz_client.get(f"{API_ROOT}/admin/modules", headers=MOB_AUTH_HEADERS)).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_reaches_non_sync_routes_only(
    authz_client: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    mock_spice_client.authenticate = AsyncMock(return_value=_contexts_for(SUPER_ADMIN_USER))  # type: ignore[method-assign]
    assert (await authz_client.get(f"{API_ROOT}/admin/modules", headers=AUTH_HEADERS)).status_code == 200
    assert (
        await authz_client.get(f"{API_ROOT}/dashboard/team-activity", headers=AUTH_HEADERS)
    ).status_code == 200
    assert (
        await authz_client.get(f"{API_ROOT}/coaching/rag-query", headers=MOB_AUTH_HEADERS)
    ).status_code == 200
    assert (await authz_client.get(f"{API_ROOT}/sync/config", headers=MOB_AUTH_HEADERS)).status_code == 403


@pytest.mark.asyncio
async def test_super_user_bypasses_route_grants(
    authz_client: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    mock_spice_client.authenticate = AsyncMock(return_value=_contexts_for(SUPER_USER))  # type: ignore[method-assign]
    assert (await authz_client.get(f"{API_ROOT}/admin/modules", headers=AUTH_HEADERS)).status_code == 200
    assert (
        await authz_client.get(f"{API_ROOT}/coaching/rag-query", headers=MOB_AUTH_HEADERS)
    ).status_code == 200
    assert (
        await authz_client.get(f"{API_ROOT}/dashboard/team-activity", headers=AUTH_HEADERS)
    ).status_code == 200


@pytest.mark.asyncio
async def test_job_user_bypasses_route_grants(
    authz_client: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    mock_spice_client.authenticate = AsyncMock(return_value=_contexts_for(JOB_USER))  # type: ignore[method-assign]
    assert (
        await authz_client.get(f"{API_ROOT}/coaching/rag-query", headers=MOB_AUTH_HEADERS)
    ).status_code == 200
    assert (await authz_client.get(f"{API_ROOT}/admin/modules", headers=AUTH_HEADERS)).status_code == 200


@pytest.mark.asyncio
async def test_uncatalogued_route_denied(
    authz_client: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    mock_spice_client.authenticate = AsyncMock(return_value=_contexts_for(AREA_MANAGER))  # type: ignore[method-assign]
    resp = await authz_client.get(f"{API_ROOT}/admin/unknown-route", headers=AUTH_HEADERS)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "insufficient role for this API"


@pytest.mark.asyncio
async def test_auth_disabled_skips_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPICE_AUTH_ENABLED", "false")
    get_settings.cache_clear()

    app = FastAPI()
    app.add_middleware(RoleRouteAuthorizationMiddleware)
    app.add_middleware(SpiceAuthMiddleware)

    @app.get(f"{API_ROOT}/admin/modules")
    async def admin_probe() -> dict[str, str]:
        return {"ok": "1"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"{API_ROOT}/admin/modules")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_authorization_denied_emits_security_log(
    authz_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
    listen_logger,
) -> None:
    listen_logger("mc.security")
    with caplog.at_level(logging.WARNING, logger="mc.security"):
        resp = await authz_client.get(
            f"{API_ROOT}/admin/modules",
            headers=AUTH_HEADERS,
        )
    assert resp.status_code == 403
    records = [record for record in caplog.records if record.name == "mc.security"]
    assert len(records) == 1
    assert records[0].event == "authorization_denied"
    assert records[0].path == f"{API_ROOT}/admin/modules"
    blob = f"{records[0].getMessage()} {records[0].__dict__}"
    assert "Authorization" not in blob
    assert VALID_TOKEN not in blob
