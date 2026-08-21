"""Tests for Redis-backed rate limiting middleware."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from platform_service.auth.rate_limit_middleware import RateLimitMiddleware
from platform_service.config import Settings, get_settings
from pydantic_settings import SettingsConfigDict

API_ROOT = "/medtronics-api"


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


@pytest_asyncio.fixture
async def rate_limit_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("API_ROOT_PATH", API_ROOT)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_RAG_PER_MINUTE", "2")
    get_settings.cache_clear()

    redis = MagicMock()
    redis.incr = AsyncMock(side_effect=[1, 2, 3])
    redis.expire = AsyncMock(return_value=True)
    monkeypatch.setattr("platform_service.auth.rate_limit_middleware.get_redis_client", lambda: redis)

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post(f"{API_ROOT}/coaching/rag-query")
    async def rag_probe() -> dict[str, str]:
        return {"status": "ok"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_threshold(rate_limit_client: AsyncClient) -> None:
    headers = {"Authorization": "Bearer test"}
    assert (
        await rate_limit_client.post(f"{API_ROOT}/coaching/rag-query", headers=headers)
    ).status_code == 200
    assert (
        await rate_limit_client.post(f"{API_ROOT}/coaching/rag-query", headers=headers)
    ).status_code == 200
    resp = await rate_limit_client.post(f"{API_ROOT}/coaching/rag-query", headers=headers)
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_emits_security_log(
    rate_limit_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
    listen_logger,
) -> None:
    listen_logger("mc.security")
    headers = {"Authorization": "Bearer test"}
    with caplog.at_level(logging.WARNING, logger="mc.security"):
        await rate_limit_client.post(f"{API_ROOT}/coaching/rag-query", headers=headers)
        await rate_limit_client.post(f"{API_ROOT}/coaching/rag-query", headers=headers)
        resp = await rate_limit_client.post(f"{API_ROOT}/coaching/rag-query", headers=headers)
    assert resp.status_code == 429
    records = [record for record in caplog.records if record.name == "mc.security"]
    assert len(records) == 1
    assert records[0].event == "rate_limit_exceeded"
    assert records[0].bucket == "rag"
    blob = f"{records[0].getMessage()} {records[0].__dict__}"
    assert "Authorization" not in blob
    assert "Bearer test" not in blob
