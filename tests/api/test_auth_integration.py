"""Full-app integration tests with SPICE auth + authorization middleware."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_contracts.morning import MorningCardsResponse
from mc_foundation.problem import register_problem_handlers
from platform_service.api.morning import router as morning_router
from platform_service.auth.rate_limit_middleware import RateLimitMiddleware
from platform_service.auth.spice_auth_middleware import SpiceAuthMiddleware
from platform_service.auth.spice_authorization_middleware import SpiceAuthorizationMiddleware
from platform_service.auth.spice_context import SpiceContexts, SpiceUserContext
from platform_service.auth.tenant_context import HEADER_TENANT_ID
from platform_service.config import Settings, get_settings
from platform_service.integrations.spice_auth_client import SpiceAuthClient
from pydantic_settings import SettingsConfigDict

from tests.conftest import platform_path

API_ROOT = "/medtronics-api"
VALID_TOKEN = "Bearer test.jwt.token"

DEVICE_USER = SpiceUserContext.model_validate(
    {
        "id": 42,
        "username": "chw_user",
        "tenantId": 7,
        "organizationIds": [7],
        "country": {"tenantId": 7},
        "roles": [{"name": "CHW", "suiteAccessName": "mob"}],
    }
)


def _contexts_for(user: SpiceUserContext) -> SpiceContexts:
    return SpiceContexts(user_detail=user, tenants=None)


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
    client.authenticate = AsyncMock(return_value=_contexts_for(DEVICE_USER))  # type: ignore[method-assign]
    return client


@pytest_asyncio.fixture
async def integration_client(
    mock_spice_client: SpiceAuthClient,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
    monkeypatch.setenv("API_ROOT_PATH", API_ROOT)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()

    app = FastAPI()
    register_problem_handlers(
        app,
        validation_error_type=RequestValidationError,
        http_exception_type=HTTPException,
    )
    api_router = APIRouter(prefix=API_ROOT)
    api_router.include_router(morning_router)
    app.include_router(api_router)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SpiceAuthorizationMiddleware)
    app.add_middleware(SpiceAuthMiddleware, client=mock_spice_client)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_device_user_cannot_query_other_chw_id(
    integration_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spoofed ``chw_id`` query param must not change whose cards are returned.

    The endpoint derives the CHW id from the authenticated principal only, so an
    attacker-supplied ``chw_id`` is ignored rather than honoured.
    """
    get_cards = AsyncMock(return_value=MorningCardsResponse(items=[], total_points=0))
    monkeypatch.setattr(
        "platform_service.api.morning.MorningSuggestionService.get_morning_cards",
        get_cards,
    )

    resp = await integration_client.get(
        platform_path("/morning/cards"),
        params={"chw_id": 99},
        headers={"Authorization": VALID_TOKEN, HEADER_TENANT_ID: "7"},
    )

    assert resp.status_code == 200
    assert get_cards.await_args is not None
    assert get_cards.await_args.kwargs["chw_id"] == DEVICE_USER.id == 42


@pytest.mark.asyncio
async def test_device_user_can_query_own_chw_id(
    integration_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "platform_service.api.morning.MorningSuggestionService.get_morning_cards",
        AsyncMock(return_value=MorningCardsResponse(items=[], total_points=0)),
    )
    resp = await integration_client.get(
        platform_path("/morning/cards"),
        params={"chw_id": 42},
        headers={"Authorization": VALID_TOKEN, HEADER_TENANT_ID: "7"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(
    integration_client: AsyncClient,
) -> None:
    resp = await integration_client.get(platform_path("/morning/cards"))
    assert resp.status_code == 401
