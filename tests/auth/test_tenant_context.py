"""Tests for country-tenant selection helpers."""

from __future__ import annotations

from platform_service.auth.spice_context import SpiceUserContext
from platform_service.auth.tenant_context import (
    DEFAULT_SELECTED_TENANT_ID,
    get_context_selected_tenant_id,
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
