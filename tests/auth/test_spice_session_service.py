"""Tests for SPICE session proxy mapping upstream failures to 401."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from platform_service.auth.spice_session_service import SpiceSessionService
from platform_service.integrations.spice_auth_client import (
    AUTH_UPSTREAM_FAILURE_DETAIL,
    SpiceAuthClient,
    SpiceAuthError,
)
from starlette.requests import Request


def _session_request() -> Request:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/session",
        "headers": [(b"content-type", b"application/json"), (b"client", b"web")],
    }
    return Request(scope, receive)


class _TimeoutClient:
    async def post(self, url: str, **kwargs: object) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")


@pytest.mark.asyncio
async def test_session_timeout_returns_401() -> None:
    client = SpiceAuthClient(base_url="http://auth.test")
    client.create_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=SpiceAuthError(401, AUTH_UPSTREAM_FAILURE_DETAIL)
    )
    service = SpiceSessionService(client=client)

    resp = await service.handle_session_request(_session_request())

    assert resp.status_code == 401
    assert json.loads(resp.body) == {"detail": AUTH_UPSTREAM_FAILURE_DETAIL}


@pytest.mark.asyncio
async def test_session_upstream_503_returns_401() -> None:
    client = SpiceAuthClient(base_url="http://auth.test")
    client.create_session = AsyncMock(  # type: ignore[method-assign]
        return_value=httpx.Response(503, text="unavailable")
    )
    service = SpiceSessionService(client=client)

    resp = await service.handle_session_request(_session_request())

    assert resp.status_code == 401
    assert json.loads(resp.body) == {"detail": AUTH_UPSTREAM_FAILURE_DETAIL}


@pytest.mark.asyncio
async def test_create_session_timeout_raises_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "platform_service.integrations.spice_auth_client.httpx.AsyncClient",
        lambda timeout, **kwargs: _TimeoutClient(),
    )
    client = SpiceAuthClient(base_url="http://auth.test", timeout=1.0)

    with pytest.raises(SpiceAuthError) as exc_info:
        await client.create_session(headers={"client": "web"}, content=b"{}")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == AUTH_UPSTREAM_FAILURE_DETAIL
