"""API integration tests for POST /sync/presigned-urls."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from mc_contracts.sync import _MAX_STORAGE_PATHS_PER_BATCH
from platform_service.api.sync import router as sync_router
from platform_service.config import Settings, get_settings
from platform_service.deps import get_db, get_object_storage_client
from pydantic_settings import SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import platform_path, requires_db

pytestmark = [requires_db, pytest.mark.asyncio]

_OBJECT_KEY = "ingest/card-media.png"


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


class _FakeStorage:
    bucket_name = "medtronics-storage"
    allowed_prefixes = frozenset({"uploads", "source-documents", "ingest"})

    async def presigned_get_url(self, **kwargs):  # type: ignore[no-untyped-def]
        return type(
            "Url",
            (),
            {"url": "https://example.test/presigned", "expires_seconds": 86400},
        )()


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


class TestSyncPresignedUrlsApi:
    async def test_presign_valid_path(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "false")
        get_settings.cache_clear()

        resp = await client.post(
            platform_path("/sync/presigned-urls"),
            json={"storage_paths": [_OBJECT_KEY]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["missing_paths"] == []
        assert len(data["urls"]) == 1
        assert data["urls"][0]["storage_path"] == _OBJECT_KEY
        assert data["urls"][0]["presigned_url"] == "https://example.test/presigned"
        assert data["urls"][0]["expires_seconds"] == get_settings().admin_file_presigned_max_seconds
        assert "server_time_utc" in data

    async def test_auth_enabled_without_user_returns_401(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
        get_settings.cache_clear()

        resp = await client.post(
            platform_path("/sync/presigned-urls"),
            json={"storage_paths": [_OBJECT_KEY]},
        )
        assert resp.status_code == 401

    async def test_batch_limit_returns_422(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "false")
        get_settings.cache_clear()

        too_many = [f"ingest/file-{i}.png" for i in range(_MAX_STORAGE_PATHS_PER_BATCH + 1)]
        resp = await client.post(
            platform_path("/sync/presigned-urls"),
            json={"storage_paths": too_many},
        )
        assert resp.status_code == 422

    async def test_empty_list_returns_422(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "false")
        get_settings.cache_clear()

        resp = await client.post(
            platform_path("/sync/presigned-urls"),
            json={"storage_paths": []},
        )
        assert resp.status_code == 422
