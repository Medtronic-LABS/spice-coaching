"""Unit tests for post-SPICE hierarchy principal enforcement."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from platform_service.auth.hierarchy_auth import enforce_hierarchy_principal
from platform_service.auth.spice_context import SpiceUserContext
from platform_service.db.models.hierarchy_user import (
    ROLE_AREA_MANAGER,
    ROLE_SHASTIYA_KORMI,
    ROLE_SUPER_ADMIN,
)
from sqlalchemy.exc import IntegrityError


def _country(tenant_id: int = 7) -> dict[str, int]:
    return {"tenantId": tenant_id}


@pytest.mark.asyncio
async def test_super_user_provisions_missing_row_then_bypasses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock(return_value=None)
    repo.ensure_super_admin_user = AsyncMock()
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate(
        {
            "id": 1,
            "firstName": "Ada",
            "lastName": "Lovelace",
            "isSuperUser": True,
            "roles": [],
            "country": _country(),
        }
    )
    assert await enforce_hierarchy_principal(MagicMock(), user) is None
    repo.ensure_super_admin_user.assert_awaited_once_with(
        user_id=1,
        name="Ada Lovelace",
        tenant_id=7,
    )


@pytest.mark.asyncio
async def test_job_user_provisions_missing_row_then_bypasses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock(return_value=None)
    repo.ensure_super_admin_user = AsyncMock()
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate(
        {
            "id": 1,
            "username": "jobber",
            "isJobUser": True,
            "roles": [],
            "country": _country(),
        }
    )
    assert await enforce_hierarchy_principal(MagicMock(), user) is None
    repo.ensure_super_admin_user.assert_awaited_once_with(
        user_id=1,
        name="jobber",
        tenant_id=7,
    )


@pytest.mark.asyncio
async def test_super_user_leaves_existing_row_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = MagicMock()
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock(return_value=existing)
    repo.ensure_super_admin_user = AsyncMock()
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate({"id": 1, "isSuperUser": True, "roles": [], "country": _country()})
    assert await enforce_hierarchy_principal(MagicMock(), user) is None
    repo.ensure_super_admin_user.assert_not_called()


@pytest.mark.asyncio
async def test_super_admin_missing_row_is_provisioned(monkeypatch: pytest.MonkeyPatch) -> None:
    created = MagicMock()
    created.role = ROLE_SUPER_ADMIN
    created.role_id = 4
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock(side_effect=[None, created])
    repo.ensure_super_admin_user = AsyncMock(return_value=created)
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate(
        {
            "id": 11,
            "roles": [{"name": ROLE_SUPER_ADMIN, "suiteAccessName": "admin"}],
            "country": _country(),
        }
    )
    assert await enforce_hierarchy_principal(MagicMock(), user) == 4
    repo.ensure_super_admin_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_display_name_falls_back_to_admin_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock(return_value=None)
    repo.ensure_super_admin_user = AsyncMock()
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate({"id": 1, "isSuperUser": True, "roles": [], "country": _country()})
    await enforce_hierarchy_principal(MagicMock(), user)
    assert repo.ensure_super_admin_user.await_args.kwargs["name"] == "Admin"


@pytest.mark.asyncio
async def test_integrity_error_on_provision_is_tolerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = MagicMock()
    session = MagicMock()
    session.rollback = AsyncMock()
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock(side_effect=[None, existing])
    repo.ensure_super_admin_user = AsyncMock(side_effect=IntegrityError("", {}, None))
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda _session: repo,
    )
    user = SpiceUserContext.model_validate({"id": 1, "isSuperUser": True, "roles": [], "country": _country()})
    assert await enforce_hierarchy_principal(session, user) is None
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_matching_role_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    hierarchy_user = MagicMock()
    hierarchy_user.role = ROLE_SHASTIYA_KORMI
    hierarchy_user.role_id = 3
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock(return_value=hierarchy_user)
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate(
        {
            "id": 42,
            "roles": [{"name": ROLE_SHASTIYA_KORMI, "suiteAccessName": "mob"}],
            "country": _country(),
        }
    )
    assert await enforce_hierarchy_principal(MagicMock(), user) == 3


@pytest.mark.asyncio
async def test_missing_row_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate(
        {
            "id": 42,
            "roles": [{"name": ROLE_SHASTIYA_KORMI, "suiteAccessName": "mob"}],
            "country": _country(),
        }
    )
    with pytest.raises(AppError) as exc:
        await enforce_hierarchy_principal(MagicMock(), user)
    assert exc.value.code == ErrorCode.HIERARCHY_AUTH_FAILED.value


@pytest.mark.asyncio
async def test_role_mismatch_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    hierarchy_user = MagicMock()
    hierarchy_user.role = ROLE_AREA_MANAGER
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock(return_value=hierarchy_user)
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate(
        {
            "id": 42,
            "roles": [{"name": ROLE_SHASTIYA_KORMI, "suiteAccessName": "mob"}],
            "country": _country(),
        }
    )
    with pytest.raises(AppError) as exc:
        await enforce_hierarchy_principal(MagicMock(), user)
    assert exc.value.code == ErrorCode.HIERARCHY_AUTH_FAILED.value
