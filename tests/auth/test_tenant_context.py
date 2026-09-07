"""Tests for country-tenant selection helpers."""

from __future__ import annotations

import pytest
from platform_service.auth.spice_context import SpiceUserContext
from platform_service.auth.tenant_context import (
    DEFAULT_SELECTED_TENANT_ID,
    HEADER_TENANT_ID,
    get_context_selected_tenant_id,
    require_selected_tenant_id,
    resolve_selected_tenant_when_auth_disabled,
    selected_tenant_from_header,
    selected_tenant_from_user,
    set_context_selected_tenant_id,
    using_selected_tenant,
)


def test_selected_tenant_from_user_returns_country_tenant_id() -> None:
    user = SpiceUserContext.model_validate(
        {
            "id": 1,
            "tenantId": 99,
            "country": {"id": 2, "name": "Kenya", "tenantId": 7},
        }
    )
    assert selected_tenant_from_user(user) == 7


def test_selected_tenant_from_user_none_when_user_missing() -> None:
    assert selected_tenant_from_user(None) is None


def test_selected_tenant_from_user_none_when_country_missing() -> None:
    user = SpiceUserContext.model_validate({"id": 1, "tenantId": 99})
    assert selected_tenant_from_user(user) is None


def test_selected_tenant_from_user_none_when_country_tenant_missing() -> None:
    user = SpiceUserContext.model_validate({"id": 1, "country": {"id": 2, "name": "Kenya"}})
    assert selected_tenant_from_user(user) is None


def test_using_selected_tenant_sets_and_resets() -> None:
    set_context_selected_tenant_id(DEFAULT_SELECTED_TENANT_ID)
    assert get_context_selected_tenant_id() == DEFAULT_SELECTED_TENANT_ID
    with using_selected_tenant(42):
        assert get_context_selected_tenant_id() == 42
        with using_selected_tenant(7):
            assert get_context_selected_tenant_id() == 7
        assert get_context_selected_tenant_id() == 42
    assert get_context_selected_tenant_id() == DEFAULT_SELECTED_TENANT_ID


def test_using_selected_tenant_resets_after_exception() -> None:
    set_context_selected_tenant_id(3)
    try:
        with using_selected_tenant(99):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert get_context_selected_tenant_id() == 3


def test_require_selected_tenant_id_fails_when_unbound() -> None:
    set_context_selected_tenant_id(DEFAULT_SELECTED_TENANT_ID)
    try:
        require_selected_tenant_id()
        raise AssertionError("expected ValueError when tenant is unbound")
    except ValueError as exc:
        assert "not bound" in str(exc)


def test_require_selected_tenant_id_returns_bound_tenant() -> None:
    with using_selected_tenant(42):
        assert require_selected_tenant_id() == 42
    try:
        require_selected_tenant_id()
        raise AssertionError("expected ValueError after using_selected_tenant exits")
    except ValueError as exc:
        assert "not bound" in str(exc)


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, DEFAULT_SELECTED_TENANT_ID),
        ({HEADER_TENANT_ID: "7"}, 7),
        ({HEADER_TENANT_ID: "  12  "}, 12),
        ({HEADER_TENANT_ID: "0"}, 0),
        ({HEADER_TENANT_ID: ""}, DEFAULT_SELECTED_TENANT_ID),
        ({HEADER_TENANT_ID: "not-a-number"}, DEFAULT_SELECTED_TENANT_ID),
    ],
)
def test_selected_tenant_from_header(headers: dict[str, str], expected: int) -> None:
    assert resolve_selected_tenant_when_auth_disabled(headers) == expected
    if expected == DEFAULT_SELECTED_TENANT_ID and HEADER_TENANT_ID not in headers:
        assert selected_tenant_from_header(headers) is None
