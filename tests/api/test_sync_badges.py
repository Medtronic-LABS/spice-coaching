"""API integration tests for GET /sync/badges."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from platform_service.api.sync import router as sync_router
from platform_service.auth.spice_identity import SYNC_AUTH_DISABLED_DEFAULT_USER_ID
from platform_service.config import Settings, get_settings
from platform_service.db.repositories.badge_repository import BadgeRepository
from platform_service.db.repositories.chw_badge_repository import CHWBadgeRepository
from platform_service.deps import get_db, get_object_storage_client
from pydantic_settings import SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import platform_path, requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setattr(
        Settings,
        "model_config",
        SettingsConfigDict(env_file=None, env_file_encoding="utf-8", extra="ignore"),
    )
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data_between_tests(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(text("TRUNCATE chw_badge, badge_module, badge RESTART IDENTITY CASCADE"))
    await db_session.commit()


class _FakeStorage:
    bucket_name = "medtronics-storage"
    allowed_prefixes = frozenset({"uploads", "source-documents", "badges"})

    async def presigned_get_url(self, **kwargs):  # type: ignore[no-untyped-def]
        return type("Url", (), {"url": "https://example.test/badge.png", "expires_seconds": 3600})()


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    app_obj = FastAPI()

    @app_obj.middleware("http")
    async def mock_auth_middleware(request: Request, call_next):
        mock_user_id = request.headers.get("x-mock-user-id")
        if mock_user_id:

            class MockSpiceUser:
                id = int(mock_user_id)
                organization_ids: list[int] = []

            request.state.spice_user = MockSpiceUser()
        return await call_next(request)

    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(sync_router)
    app_obj.include_router(api_router)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app_obj.dependency_overrides[get_db] = _override_get_db
    app_obj.dependency_overrides[get_object_storage_client] = lambda: _FakeStorage()
    yield app_obj
    app_obj.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSyncBadgesApi:
    async def test_sync_badges_uses_default_user_when_auth_disabled(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "false")
        get_settings.cache_clear()

        badge_repo = BadgeRepository(db_session)
        chw_repo = CHWBadgeRepository(db_session)
        b1 = await badge_repo.create(
            name="Dev Default Badge",
            domain="clinical",
            image_storage_path="medtronics-storage/badges/dev.png",
            tenant_id=1,
            sequence=1,
        )
        await chw_repo.try_insert_award(
            chw_id=SYNC_AUTH_DISABLED_DEFAULT_USER_ID, badge_id=b1.id, tenant_id=1
        )
        await db_session.commit()

        resp = await client.get(platform_path("/sync/badges"))
        assert resp.status_code == 200
        assert len(resp.json()["earned_badges"]) == 1
        assert resp.json()["earned_badges"][0]["id"] == str(b1.id)

    async def test_sync_badges_returns_available_and_earned(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
        get_settings.cache_clear()

        badge_repo = BadgeRepository(db_session)
        chw_repo = CHWBadgeRepository(db_session)

        b1 = await badge_repo.create(
            name="Clinical Specialist",
            domain="clinical",
            image_storage_path="medtronics-storage/badges/clinical.png",
            tenant_id=1,
            sequence=1,
        )

        b2 = await badge_repo.create(
            name="Digital Master",
            domain="digital",
            image_storage_path="medtronics-storage/badges/digital.png",
            tenant_id=1,
            sequence=2,
        )

        # CHW 42 earns b1
        await chw_repo.try_insert_award(chw_id=42, badge_id=b1.id, tenant_id=1)
        await db_session.commit()

        resp = await client.get(
            platform_path("/sync/badges"),
            headers={"x-mock-user-id": "42"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "available_badges" in data
        assert "earned_badges" in data
        assert "server_time_utc" in data

        avail = data["available_badges"]
        assert len(avail) == 2
        assert avail[0]["id"] == str(b1.id)
        assert avail[0]["name"] == "Clinical Specialist"
        assert avail[0]["image_presigned_url"] == "https://example.test/badge.png"
        assert avail[0]["image_storage_path"] == "badges/clinical.png"
        assert avail[1]["id"] == str(b2.id)
        assert avail[1]["image_storage_path"] == "badges/digital.png"

        earned = data["earned_badges"]
        assert len(earned) == 1
        assert earned[0]["id"] == str(b1.id)
        assert earned[0]["name"] == "Clinical Specialist"
        assert "earned_at" in earned[0]
