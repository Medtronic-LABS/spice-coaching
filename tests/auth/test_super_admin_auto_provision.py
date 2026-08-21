"""DB-backed auto-provision of SUPER_ADMIN hierarchy users on auth."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from platform_service.auth.api_route_catalog import ALL_PATH_TEMPLATES, path_templates_for_role
from platform_service.auth.hierarchy_auth import enforce_hierarchy_principal
from platform_service.auth.role_route_authorization_middleware import (
    RoleRouteAuthorizationMiddleware,
)
from platform_service.auth.spice_auth_middleware import SpiceAuthMiddleware
from platform_service.auth.spice_context import SpiceContexts, SpiceUserContext
from platform_service.auth.tenant_context import HEADER_TENANT_ID
from platform_service.config import Settings, get_settings
from platform_service.db.models.hierarchy_user import ROLE_SUPER_ADMIN
from platform_service.db.models.role import Role
from platform_service.db.repositories.hierarchy_repository import HierarchyRepository
from platform_service.integrations.spice_auth_client import SpiceAuthClient
from pydantic_settings import SettingsConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio]

API_ROOT = "/medtronics-api"
AUTH_HEADERS = {"Authorization": "Bearer test.jwt.token", HEADER_TENANT_ID: "1", "client": "web"}
SUPER_USER_ID = 91001
SUPER_ADMIN_ID = 91002


async def _ensure_super_admin_role(session: AsyncSession) -> Role:
    existing = (await session.execute(select(Role).where(Role.code == ROLE_SUPER_ADMIN))).scalar_one_or_none()
    if existing is not None:
        return existing
    row = Role(code=ROLE_SUPER_ADMIN)
    session.add(row)
    await session.flush()
    return row


@pytest_asyncio.fixture(autouse=True)
async def _wipe_users(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(text('DELETE FROM "users" WHERE id IN (91001, 91002)'))
    await db_session.commit()


async def test_enforce_provisions_super_user_row(db_session: AsyncSession) -> None:
    await _ensure_super_admin_role(db_session)
    await db_session.commit()

    user = SpiceUserContext.model_validate(
        {
            "id": SUPER_USER_ID,
            "firstName": "Super",
            "lastName": "User",
            "isSuperUser": True,
            "roles": [],
            "country": {"tenantId": 1},
        }
    )
    assert await enforce_hierarchy_principal(db_session, user) is None
    await db_session.commit()

    row = await HierarchyRepository(db_session).get_user_by_id(SUPER_USER_ID)
    assert row is not None
    assert row.name == "Super User"
    assert row.role == ROLE_SUPER_ADMIN
    assert row.parent_id is None
    assert row.district_id is None
    assert row.tenant_id == 1

    # Second call must not rewrite the row.
    row.name = "Changed"
    await db_session.commit()
    assert await enforce_hierarchy_principal(db_session, user) is None
    await db_session.commit()
    refreshed = await HierarchyRepository(db_session).get_user_by_id(SUPER_USER_ID)
    assert refreshed is not None
    assert refreshed.name == "Changed"


async def test_super_admin_request_auto_provisions_and_reaches_admin_route(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    role = await _ensure_super_admin_role(db_session)
    await db_session.commit()

    spice_user = SpiceUserContext.model_validate(
        {
            "id": SUPER_ADMIN_ID,
            "username": "sa",
            "isSuperUser": False,
            "roles": [{"name": ROLE_SUPER_ADMIN, "suiteAccessName": "admin"}],
            "country": {"tenantId": 1},
        }
    )
    assert (await HierarchyRepository(db_session).get_user_by_id(SUPER_ADMIN_ID)) is None

    get_settings.cache_clear()
    monkeypatch.setattr(
        Settings,
        "model_config",
        SettingsConfigDict(env_file=None, env_file_encoding="utf-8", extra="ignore"),
    )
    monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
    monkeypatch.setenv("API_ROOT_PATH", "/medtronics-api")
    get_settings.cache_clear()

    spice_client = SpiceAuthClient(base_url="http://auth.test")
    spice_client.authenticate = AsyncMock(  # type: ignore[method-assign]
        return_value=SpiceContexts(user_detail=spice_user, tenants=None)
    )

    class _FakeRoleRouteAccessRepository:
        def __init__(self, _session: Any) -> None:
            pass

        async def list_all_path_templates(self) -> list[str]:
            return list(ALL_PATH_TEMPLATES)

        async def list_path_templates_for_role(self, role_id: int) -> list[str]:
            if role_id != role.id:
                return []
            return list(path_templates_for_role(ROLE_SUPER_ADMIN))

    @asynccontextmanager
    async def _session_for_role_mw() -> AsyncIterator[AsyncSession]:
        # Role middleware opens its own session; reuse the test engine pool.
        from platform_service.db.base import SessionLocal

        async with SessionLocal() as session:
            yield session

    monkeypatch.setattr(
        "platform_service.auth.role_route_authorization_middleware.SessionLocal",
        _session_for_role_mw,
    )
    monkeypatch.setattr(
        "platform_service.auth.role_route_authorization_middleware.RoleRouteAccessRepository",
        _FakeRoleRouteAccessRepository,
    )

    app = FastAPI()
    app.add_middleware(RoleRouteAuthorizationMiddleware)
    app.add_middleware(SpiceAuthMiddleware, client=spice_client)

    @app.get(f"{API_ROOT}/admin/modules")
    async def admin_probe() -> dict[str, str]:
        return {"plane": "admin"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"{API_ROOT}/admin/modules", headers=AUTH_HEADERS)

    assert response.status_code == 200, response.text

    # Middleware committed on its own SessionLocal; refresh via new query after expire.
    await db_session.rollback()
    row = await HierarchyRepository(db_session).get_user_by_id(SUPER_ADMIN_ID)
    assert row is not None
    assert row.name == "sa"
    assert row.role == ROLE_SUPER_ADMIN
    assert row.district_id is None
    assert row.parent_id is None

    get_settings.cache_clear()
