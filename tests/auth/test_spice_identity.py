"""Tests for SPICE identity binding on device-plane routes."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from mc_foundation.problem import AppError
from platform_service.auth.spice_context import SpiceUserContext
from platform_service.auth.spice_identity import (
    SYNC_AUTH_DISABLED_DEFAULT_USER_ID,
    require_chw_id_for_device_route,
    require_chw_id_for_telemetry,
    resolve_chw_id_for_device_route,
    resolve_sync_user_id,
    resolve_tenant_id_for_device_route,
)
from platform_service.config import Settings, get_settings
from pydantic_settings import SettingsConfigDict
from starlette.requests import Request


def _request_with_user(user: SpiceUserContext | None, *, selected_tenant_id: int = 7) -> Request:
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    request = Request(scope)
    if user is not None:
        request.state.spice_user = user
    request.state.selected_tenant_id = selected_tenant_id
    return request


DEVICE_USER = SpiceUserContext.model_validate(
    {
        "id": 42,
        "username": "chw_user",
        "tenantId": 7,
        "organizationIds": [7],
        "roles": [{"name": "CHW", "suiteAccessName": "mob"}],
    }
)
ADMIN_USER = SpiceUserContext.model_validate(
    {"id": 1, "username": "admin", "organizationIds": [7], "roles": [{"name": "AREA_MANAGER"}]}
)


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


class TestSpiceIdentityDisabled:
    def test_passes_through_when_auth_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "false")
        get_settings.cache_clear()
        request = _request_with_user(None, selected_tenant_id=0)
        assert resolve_chw_id_for_device_route(request, 99) == 99
        assert require_chw_id_for_telemetry(request, 99) == 99
        assert resolve_tenant_id_for_device_route(request, None) == 0

    def test_resolve_sync_user_id_defaults_when_auth_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "false")
        get_settings.cache_clear()
        request = _request_with_user(DEVICE_USER)
        assert resolve_sync_user_id(request) == SYNC_AUTH_DISABLED_DEFAULT_USER_ID


class TestSpiceIdentityEnabled:
    @pytest.fixture(autouse=True)
    def _enable_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
        get_settings.cache_clear()

    def test_device_user_cannot_override_chw_id(self) -> None:
        request = _request_with_user(DEVICE_USER)
        with pytest.raises(AppError) as exc:
            resolve_chw_id_for_device_route(request, 99)
        assert exc.value.status == 403

    def test_device_user_gets_own_chw_id_when_omitted(self) -> None:
        request = _request_with_user(DEVICE_USER)
        assert resolve_chw_id_for_device_route(request, None) == 42

    def test_device_user_matching_chw_id(self) -> None:
        request = _request_with_user(DEVICE_USER)
        assert require_chw_id_for_device_route(request, 42) == 42

    def test_telemetry_rejects_mismatched_batch_chw_id(self) -> None:
        request = _request_with_user(DEVICE_USER)
        with pytest.raises(AppError) as exc:
            require_chw_id_for_telemetry(request, 99)
        assert exc.value.status == 403

    def test_telemetry_accepts_matching_batch_chw_id(self) -> None:
        request = _request_with_user(DEVICE_USER)
        assert require_chw_id_for_telemetry(request, 42) == 42

    def test_admin_may_query_other_chw_id(self) -> None:
        request = _request_with_user(ADMIN_USER)
        assert resolve_chw_id_for_device_route(request, 99) == 99

    def test_selected_tenant_comes_from_request_state(self) -> None:
        request = _request_with_user(DEVICE_USER, selected_tenant_id=7)
        assert resolve_tenant_id_for_device_route(request, 999) == 7

    def test_unauthenticated_raises_401(self) -> None:
        request = _request_with_user(None)
        with pytest.raises(AppError) as exc:
            resolve_chw_id_for_device_route(request, 1)
        assert exc.value.status == 401

    def test_resolve_sync_user_id_returns_device_user_id(self) -> None:
        request = _request_with_user(DEVICE_USER)
        assert resolve_sync_user_id(request) == 42

    def test_resolve_sync_user_id_unauthenticated_raises_401(self) -> None:
        request = _request_with_user(None)
        with pytest.raises(AppError) as exc:
            resolve_sync_user_id(request)
        assert exc.value.status == 401

    def test_resolve_sync_user_id_raises_when_user_has_no_id(self) -> None:
        user = SpiceUserContext.model_validate(
            {"username": "anon", "organizationIds": [7], "roles": [{"name": "CHW", "suiteAccessName": "mob"}]}
        )
        request = _request_with_user(user)
        with pytest.raises(AppError) as exc:
            resolve_sync_user_id(request)
        assert exc.value.status == 403
