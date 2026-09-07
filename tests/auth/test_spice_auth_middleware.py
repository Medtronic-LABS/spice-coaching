"""Tests for SPICE auth middleware and SpiceAuthClient."""

from __future__ import annotations

import base64
import logging
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mc_contracts.errors import ErrorCode
from platform_service.auth.spice_auth_middleware import SpiceAuthMiddleware
from platform_service.auth.spice_context import SpiceContexts
from platform_service.auth.tenant_context import DEFAULT_SELECTED_TENANT_ID, HEADER_TENANT_ID
from platform_service.config import Settings, get_settings
from platform_service.integrations.spice_auth_client import (
    SpiceAuthClient,
    SpiceAuthError,
)
from platform_service.main import create_app
from pydantic_settings import SettingsConfigDict
from starlette.requests import Request

API_ROOT = "/medtronics-api"
VALID_TOKEN = "Bearer test.jwt.token"
MOCK_CONTEXTS = SpiceContexts.model_validate(
    {
        "userDetail": {
            "id": 42,
            "username": "chw_user",
            "tenantId": 1,
            "organizationIds": [1, 7],
            "country": {"tenantId": 7},
        },
        "tenants": None,
    }
)


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
        AsyncMock(return_value=None),
    )
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_spice_client() -> SpiceAuthClient:
    client = SpiceAuthClient(base_url="http://auth.test")
    client.authenticate = AsyncMock(return_value=MOCK_CONTEXTS)  # type: ignore[method-assign]
    return client


@pytest_asyncio.fixture
async def middleware_app(
    mock_spice_client: SpiceAuthClient,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
    monkeypatch.setenv("API_ROOT_PATH", "/medtronics-api")
    get_settings.cache_clear()

    app = FastAPI()
    app.add_middleware(SpiceAuthMiddleware, client=mock_spice_client)

    @app.get(f"{API_ROOT}/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(f"{API_ROOT}/probe")
    async def probe(request: Request) -> dict[str, int | None]:
        return {
            "ok": 1,
            "selected_tenant_id": getattr(request.state, "selected_tenant_id", None),
        }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_disabled_auth_allows_request_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_ROOT_PATH", "/medtronics-api")
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Prefer a dependency-free route: /ready probes Postgres/Redis/etc.
        resp = await client.get(f"{API_ROOT}/openapi.json")
    assert resp.status_code == 200
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def disabled_auth_middleware_app(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("SPICE_AUTH_ENABLED", "false")
    monkeypatch.setenv("API_ROOT_PATH", "/medtronics-api")
    get_settings.cache_clear()

    app = FastAPI()
    app.add_middleware(SpiceAuthMiddleware)

    @app.get(f"{API_ROOT}/probe")
    async def probe(request: Request) -> dict[str, int | None]:
        return {
            "ok": 1,
            "selected_tenant_id": getattr(request.state, "selected_tenant_id", None),
        }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_disabled_auth_defaults_tenant_to_zero(
    disabled_auth_middleware_app: AsyncClient,
) -> None:
    resp = await disabled_auth_middleware_app.get(f"{API_ROOT}/probe")
    assert resp.status_code == 200
    assert resp.json()["selected_tenant_id"] == DEFAULT_SELECTED_TENANT_ID


@pytest.mark.asyncio
async def test_disabled_auth_uses_tenant_header(
    disabled_auth_middleware_app: AsyncClient,
) -> None:
    resp = await disabled_auth_middleware_app.get(
        f"{API_ROOT}/probe",
        headers={HEADER_TENANT_ID: "42"},
    )
    assert resp.status_code == 200
    assert resp.json()["selected_tenant_id"] == 42


@pytest.mark.asyncio
async def test_enabled_missing_token_returns_401(middleware_app: AsyncClient) -> None:
    resp = await middleware_app.get(f"{API_ROOT}/probe")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing or invalid Authorization header"


@pytest.mark.asyncio
async def test_enabled_invalid_token_prefix_returns_401(middleware_app: AsyncClient) -> None:
    resp = await middleware_app.get(
        f"{API_ROOT}/probe",
        headers={"Authorization": "Token abc"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_enabled_valid_token_uses_country_tenant(
    middleware_app: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    resp = await middleware_app.get(
        f"{API_ROOT}/probe",
        headers={"Authorization": VALID_TOKEN, "client": "mob", HEADER_TENANT_ID: "99"},
    )
    assert resp.status_code == 200
    assert resp.json()["selected_tenant_id"] == 7
    mock_spice_client.authenticate.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_enabled_ignores_request_tenant_header(
    middleware_app: AsyncClient,
) -> None:
    resp = await middleware_app.get(
        f"{API_ROOT}/probe",
        headers={"Authorization": VALID_TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["selected_tenant_id"] == 7


@pytest.mark.asyncio
async def test_enabled_missing_country_tenant_returns_401(
    middleware_app: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    mock_spice_client.authenticate = AsyncMock(  # type: ignore[method-assign]
        return_value=SpiceContexts.model_validate(
            {
                "userDetail": {
                    "id": 42,
                    "username": "chw_user",
                    "tenantId": 1,
                    "organizationIds": [1, 7],
                },
                "tenants": None,
            }
        )
    )
    resp = await middleware_app.get(
        f"{API_ROOT}/probe",
        headers={"Authorization": VALID_TOKEN},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == ErrorCode.NOT_AUTHENTICATED.value
    assert "country.tenantId" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_enabled_country_tenant_not_in_organization_ids_still_allowed(
    middleware_app: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    mock_spice_client.authenticate = AsyncMock(  # type: ignore[method-assign]
        return_value=SpiceContexts.model_validate(
            {
                "userDetail": {
                    "id": 42,
                    "username": "chw_user",
                    "organizationIds": [1],
                    "country": {"tenantId": 55},
                },
                "tenants": None,
            }
        )
    )
    resp = await middleware_app.get(
        f"{API_ROOT}/probe",
        headers={"Authorization": VALID_TOKEN, HEADER_TENANT_ID: "1"},
    )
    assert resp.status_code == 200
    assert resp.json()["selected_tenant_id"] == 55


@pytest.mark.asyncio
async def test_ready_exempt_when_auth_enabled(middleware_app: AsyncClient) -> None:
    resp = await middleware_app.get(f"{API_ROOT}/ready")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_spice_auth_failure_returns_401(
    middleware_app: AsyncClient, mock_spice_client: SpiceAuthClient
) -> None:
    mock_spice_client.authenticate = AsyncMock(  # type: ignore[method-assign]
        side_effect=SpiceAuthError(401, "invalid or expired token")
    )
    resp = await middleware_app.get(
        f"{API_ROOT}/probe",
        headers={"Authorization": VALID_TOKEN, HEADER_TENANT_ID: "7"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_spice_auth_unavailable_returns_401(
    middleware_app: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    mock_spice_client.authenticate = AsyncMock(  # type: ignore[method-assign]
        side_effect=SpiceAuthError(401, "unable to authenticate")
    )
    resp = await middleware_app.get(
        f"{API_ROOT}/probe",
        headers={"Authorization": VALID_TOKEN, HEADER_TENANT_ID: "7"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == ErrorCode.NOT_AUTHENTICATED.value


def test_spice_auth_exempt_path_set_default() -> None:
    s = Settings()
    assert f"{s.api_root_path_normalized}/ready" in s.spice_auth_exempt_path_set
    assert f"{s.api_root_path_normalized}/docs" in s.spice_auth_exempt_path_set
    assert f"{s.api_root_path_normalized}/openapi.json" in s.spice_auth_exempt_path_set
    assert f"{s.api_root_path_normalized}/health" not in s.spice_auth_exempt_path_set


@pytest.mark.asyncio
async def test_web_client_auth_cookie_resolution_and_set_cookie(
    middleware_app: AsyncClient,
    mock_spice_client: SpiceAuthClient,
) -> None:
    token_raw = "test.jwt.token"
    encoded_token = base64.b64encode(token_raw.encode("utf-8")).decode("utf-8")

    resp = await middleware_app.get(
        f"{API_ROOT}/probe",
        headers={"client": "web", HEADER_TENANT_ID: "7"},
        cookies={"auth-cookie": encoded_token},
    )
    assert resp.status_code == 200
    assert resp.json()["selected_tenant_id"] == 7
    mock_spice_client.authenticate.assert_awaited_once()  # type: ignore[attr-defined]
    assert "set-cookie" in resp.headers
    assert "auth-cookie=" in resp.headers["set-cookie"]


def test_spice_auth_authenticate_url() -> None:
    s = Settings(spice_auth_base_url="http://gateway/auth-service")
    assert s.spice_auth_authenticate_url == "http://gateway/auth-service/authenticate"


@pytest.mark.asyncio
async def test_spice_auth_client_success(monkeypatch: pytest.MonkeyPatch) -> None:
    contexts_payload = {"userDetail": {"id": 7, "username": "u"}, "tenants": []}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/authenticate"
        assert request.headers["Authorization"] == VALID_TOKEN
        assert request.headers["client"] == "mob"
        return httpx.Response(200, json=contexts_payload)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "platform_service.integrations.spice_auth_client.httpx.AsyncClient",
        lambda timeout, **kwargs: _MockClientContext(transport, timeout),
    )
    client = SpiceAuthClient(base_url="http://auth.test", timeout=1.0)
    result = await client.authenticate(authorization=VALID_TOKEN, client="mob")
    assert result.user_detail is not None
    assert result.user_detail.id == 7


class _MockClientContext:
    def __init__(self, transport: httpx.MockTransport, timeout: float) -> None:
        self._transport = transport

    async def __aenter__(self) -> _MockClientContext:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
        request = httpx.Request("POST", url, headers=kwargs.get("headers"))
        return self._transport.handle_request(request)


@pytest.mark.asyncio
async def test_spice_auth_client_4xx_maps_to_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, json={"error": "forbidden"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "platform_service.integrations.spice_auth_client.httpx.AsyncClient",
        lambda timeout, **kwargs: _MockClientContext(transport, timeout),
    )
    monkeypatch.setattr(
        "platform_service.integrations.spice_auth_client.asyncio.sleep",
        AsyncMock(),
    )
    client = SpiceAuthClient(base_url="http://auth.test", timeout=1.0)
    with pytest.raises(SpiceAuthError) as exc_info:
        await client.authenticate(authorization=VALID_TOKEN)
    assert exc_info.value.status_code == 401
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_spice_auth_client_retries_5xx_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts_payload = {"userDetail": {"id": 7, "username": "u"}, "tenants": []}
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json=contexts_payload)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "platform_service.integrations.spice_auth_client.httpx.AsyncClient",
        lambda timeout, **kwargs: _MockClientContext(transport, timeout),
    )
    sleep = AsyncMock()
    monkeypatch.setattr(
        "platform_service.integrations.spice_auth_client.asyncio.sleep",
        sleep,
    )
    client = SpiceAuthClient(base_url="http://auth.test", timeout=1.0)
    result = await client.authenticate(authorization=VALID_TOKEN, client="mob")
    assert result.user_detail is not None
    assert result.user_detail.id == 7
    assert calls["n"] == 3
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_spice_auth_client_retries_timeout_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts_payload = {"userDetail": {"id": 7, "username": "u"}, "tenants": []}
    calls = {"n": 0}

    async def flaky_post(self: _MockClientContext, url: str, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("timed out")
        request = httpx.Request("POST", url, headers=kwargs.get("headers"))
        return self._transport.handle_request(request)

    monkeypatch.setattr(
        "platform_service.integrations.spice_auth_client.httpx.AsyncClient",
        lambda timeout, **kwargs: _MockClientContext(
            httpx.MockTransport(lambda r: httpx.Response(200, json=contexts_payload)),
            timeout,
        ),
    )
    monkeypatch.setattr(_MockClientContext, "post", flaky_post)
    sleep = AsyncMock()
    monkeypatch.setattr(
        "platform_service.integrations.spice_auth_client.asyncio.sleep",
        sleep,
    )
    client = SpiceAuthClient(base_url="http://auth.test", timeout=1.0)
    result = await client.authenticate(authorization=VALID_TOKEN)
    assert result.user_detail is not None
    assert result.user_detail.id == 7
    assert calls["n"] == 2
    assert sleep.await_count == 1


@pytest.mark.asyncio
async def test_spice_auth_client_exhausts_retries_on_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(502, text="bad gateway")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "platform_service.integrations.spice_auth_client.httpx.AsyncClient",
        lambda timeout, **kwargs: _MockClientContext(transport, timeout),
    )
    sleep = AsyncMock()
    monkeypatch.setattr(
        "platform_service.integrations.spice_auth_client.asyncio.sleep",
        sleep,
    )
    client = SpiceAuthClient(base_url="http://auth.test", timeout=1.0)
    with pytest.raises(SpiceAuthError) as exc_info:
        await client.authenticate(authorization=VALID_TOKEN)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "unable to authenticate"
    assert calls["n"] == 3
    assert sleep.await_count == 2


def _assert_no_secrets(records: list[logging.LogRecord]) -> None:
    for record in records:
        blob = f"{record.getMessage()} {record.__dict__}"
        assert "Authorization" not in blob
        assert "auth-cookie" not in blob
        assert VALID_TOKEN not in blob


@pytest.mark.asyncio
async def test_auth_success_emits_audit_log(
    middleware_app: AsyncClient,
    caplog: pytest.LogCaptureFixture,
    listen_logger,
) -> None:
    listen_logger("mc.audit")
    with caplog.at_level(logging.INFO, logger="mc.audit"):
        resp = await middleware_app.get(
            f"{API_ROOT}/probe",
            headers={"Authorization": VALID_TOKEN, "client": "mob"},
        )
    assert resp.status_code == 200
    records = [record for record in caplog.records if record.name == "mc.audit"]
    assert len(records) == 1
    assert records[0].event == "auth_success"
    assert records[0].user_id == 42
    assert records[0].tenant_id == 7
    assert records[0].path == f"{API_ROOT}/probe"
    assert records[0].client == "mob"
    _assert_no_secrets(records)


@pytest.mark.asyncio
async def test_auth_failure_emits_security_log(
    middleware_app: AsyncClient,
    caplog: pytest.LogCaptureFixture,
    listen_logger,
) -> None:
    listen_logger("mc.security")
    with caplog.at_level(logging.WARNING, logger="mc.security"):
        resp = await middleware_app.get(f"{API_ROOT}/probe")
    assert resp.status_code == 401
    records = [record for record in caplog.records if record.name == "mc.security"]
    assert len(records) == 1
    assert records[0].event == "auth_failure"
    assert records[0].status == 401
    assert records[0].path == f"{API_ROOT}/probe"
    _assert_no_secrets(records)
