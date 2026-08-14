"""Configs API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_foundation.problem import register_problem_handlers
from platform_service.api.configs import router as configs_router
from platform_service.config import get_settings
from platform_service.deps import get_db
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import platform_path, requires_db

pytestmark = [requires_db, pytest.mark.asyncio]

_SEED_CONFIG_SQL = """
INSERT INTO config_threshold (tenant_id, key, title, description) VALUES
(
    0,
    'quiz_reattempt_validity_days',
    'Quiz Reattempt Validity (Days)',
    'Configure the number of days from the module assignment date during which users can reattempt a quiz. Users are always allowed their first quiz attempt, even if this period has expired. After the first attempt, reattempts are permitted only until the configured validity period ends.'
)
ON CONFLICT ON CONSTRAINT uq_config_threshold_tenant_key DO NOTHING;

INSERT INTO config_threshold_change (
    tenant_id,
    config_threshold_id,
    key,
    previous_value_json,
    current_value_json,
    version,
    updated_by
)
SELECT
    ct.tenant_id,
    ct.id,
    ct.key,
    NULL,
    '30'::jsonb,
    1,
    'test'
FROM config_threshold AS ct
WHERE ct.key = 'quiz_reattempt_validity_days'
  AND ct.tenant_id = 0
  AND NOT EXISTS (
      SELECT 1
      FROM config_threshold_change AS ctc
      WHERE ctc.config_threshold_id = ct.id
  );
"""


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    app_obj = FastAPI()
    register_problem_handlers(
        app_obj,
        validation_error_type=RequestValidationError,
        http_exception_type=HTTPException,
    )
    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(configs_router)
    app_obj.include_router(api_router)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app_obj.dependency_overrides[get_db] = _override_get_db
    yield app_obj
    app_obj.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _wipe_and_seed_data(db_session: AsyncSession) -> AsyncIterator[None]:
    await db_session.execute(text(_SEED_CONFIG_SQL))
    await db_session.commit()

    yield

    await db_session.rollback()
    await db_session.execute(
        text("TRUNCATE config_threshold_change, config_threshold RESTART IDENTITY CASCADE")
    )
    await db_session.commit()


class TestConfigsRoutes:
    async def test_list_configs(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/configs"))
        assert resp.status_code == 200
        data = resp.json()
        keys = [item["key"] for item in data]
        assert "quiz_reattempt_validity_days" in keys

        duration_config = next(item for item in data if item["key"] == "quiz_reattempt_validity_days")
        assert duration_config["value_json"] == 30
        assert duration_config["title"] == "Quiz Reattempt Validity (Days)"
        assert duration_config["version"] == 1
        assert duration_config["updated_by"] == "test"

    async def test_get_config_by_key(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/configs/quiz_reattempt_validity_days"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "quiz_reattempt_validity_days"
        assert data["value_json"] == 30
        assert data["title"] == "Quiz Reattempt Validity (Days)"
        assert data["version"] == 1

        resp_missing = await client.get(platform_path("/admin/configs/non_existent_key"))
        assert resp_missing.status_code == 404

    async def test_update_config(self, client: AsyncClient) -> None:
        resp = await client.put(
            platform_path("/admin/configs/quiz_reattempt_validity_days"),
            json={"value_json": 45, "title": "Updated Title", "description": "Updated description"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "quiz_reattempt_validity_days"
        assert data["value_json"] == 45
        assert data["title"] == "Updated Title"
        assert data["description"] == "Updated description"
        assert data["version"] == 2
        assert data["updated_by"] == "admin"

        resp_missing = await client.put(
            platform_path("/admin/configs/non_existent_key"), json={"value_json": 12}
        )
        assert resp_missing.status_code == 404

    async def test_update_config_same_value_does_not_append_change(self, client: AsyncClient) -> None:
        resp = await client.put(
            platform_path("/admin/configs/quiz_reattempt_validity_days"),
            json={"value_json": 30},
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 1

        history = await client.get(platform_path("/admin/configs/quiz_reattempt_validity_days/changes"))
        assert history.status_code == 200
        assert history.json()["total_changes"] == 1

    async def test_list_config_changes(self, client: AsyncClient) -> None:
        await client.put(
            platform_path("/admin/configs/quiz_reattempt_validity_days"),
            json={"value_json": 45},
        )
        await client.put(
            platform_path("/admin/configs/quiz_reattempt_validity_days"),
            json={"value_json": 60},
        )

        resp = await client.get(platform_path("/admin/configs/quiz_reattempt_validity_days/changes"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_changes"] == 3
        assert data["total_pages"] == 1
        assert data["limit"] == 50
        assert data["offset"] == 0

        newest, middle, oldest = data["changes"]
        assert newest["current_value_json"] == 60
        assert newest["previous_value_json"] == 45
        assert newest["updated_by"] == "admin"
        assert middle["current_value_json"] == 45
        assert middle["previous_value_json"] == 30
        assert oldest["current_value_json"] == 30
        assert oldest["previous_value_json"] is None
        assert oldest["updated_by"] == "test"

        page = await client.get(
            platform_path("/admin/configs/quiz_reattempt_validity_days/changes"),
            params={"limit": 1, "offset": 1},
        )
        assert page.status_code == 200
        page_data = page.json()
        assert page_data["total_changes"] == 3
        assert page_data["total_pages"] == 3
        assert len(page_data["changes"]) == 1
        assert page_data["changes"][0]["current_value_json"] == 45

        missing = await client.get(platform_path("/admin/configs/non_existent_key/changes"))
        assert missing.status_code == 404
