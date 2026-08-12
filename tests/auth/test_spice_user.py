"""Tests for SPICE user helpers."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from mc_foundation.problem import AppError
from platform_service.auth.spice_context import SpiceUserContext
from platform_service.auth.spice_user import (
    resolve_optional_spice_actor,
    resolve_spice_actor,
    resolve_spice_user_id,
)
from platform_service.config import Settings, get_settings
from pydantic_settings import SettingsConfigDict


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


def test_resolve_spice_actor_defaults_to_admin_when_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPICE_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    request = SimpleNamespace(state=SimpleNamespace(spice_user=None))
    assert resolve_spice_actor(request) == "admin"  # type: ignore[arg-type]


def test_resolve_spice_actor_raises_when_auth_enabled_and_no_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
    get_settings.cache_clear()
    request = SimpleNamespace(state=SimpleNamespace(spice_user=None))
    with pytest.raises(AppError) as exc:
        resolve_spice_actor(request)  # type: ignore[arg-type]
    assert exc.value.status == 401


def test_resolve_spice_actor_uses_username() -> None:
    user = SpiceUserContext.model_validate({"id": 1, "username": "region_admin"})
    request = SimpleNamespace(state=SimpleNamespace(spice_user=user))
    assert resolve_spice_actor(request) == "region_admin"  # type: ignore[arg-type]


def test_resolve_spice_actor_falls_back_to_user_id() -> None:
    user = SpiceUserContext.model_validate({"id": 42})
    request = SimpleNamespace(state=SimpleNamespace(spice_user=user))
    assert resolve_spice_actor(request) == "42"  # type: ignore[arg-type]


def test_resolve_spice_actor_defaults_when_user_has_no_identity() -> None:
    user = SpiceUserContext.model_validate({})
    request = SimpleNamespace(state=SimpleNamespace(spice_user=user))
    assert resolve_spice_actor(request) == "admin"  # type: ignore[arg-type]


def test_resolve_optional_spice_actor_returns_none_when_no_user() -> None:
    request = SimpleNamespace(state=SimpleNamespace(spice_user=None))
    assert resolve_optional_spice_actor(request) is None  # type: ignore[arg-type]


def test_resolve_optional_spice_actor_uses_username() -> None:
    user = SpiceUserContext.model_validate({"id": 1, "username": "badge_admin"})
    request = SimpleNamespace(state=SimpleNamespace(spice_user=user))
    assert resolve_optional_spice_actor(request) == "badge_admin"  # type: ignore[arg-type]


def test_resolve_optional_spice_actor_falls_back_to_user_id() -> None:
    user = SpiceUserContext.model_validate({"id": 99})
    request = SimpleNamespace(state=SimpleNamespace(spice_user=user))
    assert resolve_optional_spice_actor(request) == "99"  # type: ignore[arg-type]


def test_resolve_optional_spice_actor_returns_none_when_user_has_no_identity() -> None:
    user = SpiceUserContext.model_validate({})
    request = SimpleNamespace(state=SimpleNamespace(spice_user=user))
    assert resolve_optional_spice_actor(request) is None  # type: ignore[arg-type]


def test_resolve_spice_user_id_returns_none_when_no_user() -> None:
    request = SimpleNamespace(state=SimpleNamespace(spice_user=None))
    assert resolve_spice_user_id(request) is None  # type: ignore[arg-type]


def test_resolve_spice_user_id_returns_int_id() -> None:
    user = SpiceUserContext.model_validate({"id": 42, "username": "admin"})
    request = SimpleNamespace(state=SimpleNamespace(spice_user=user))
    assert resolve_spice_user_id(request) == 42  # type: ignore[arg-type]


def test_resolve_spice_user_id_returns_none_when_user_has_no_id() -> None:
    user = SpiceUserContext.model_validate({"username": "admin"})
    request = SimpleNamespace(state=SimpleNamespace(spice_user=user))
    assert resolve_spice_user_id(request) is None  # type: ignore[arg-type]
