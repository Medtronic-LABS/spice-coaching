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
)


@pytest.mark.asyncio
async def test_super_user_bypasses_hierarchy(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock()
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate({"id": 1, "isSuperUser": True, "roles": []})
    await enforce_hierarchy_principal(MagicMock(), user)
    repo.get_user_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_job_user_bypasses_hierarchy(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock()
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate({"id": 1, "isJobUser": True, "roles": []})
    await enforce_hierarchy_principal(MagicMock(), user)
    repo.get_user_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_matching_role_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    hierarchy_user = MagicMock()
    hierarchy_user.role = ROLE_SHASTIYA_KORMI
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
        }
    )
    await enforce_hierarchy_principal(MagicMock(), user)


@pytest.mark.asyncio
async def test_missing_row_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MagicMock()
    repo.get_user_by_id = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "platform_service.auth.hierarchy_auth.HierarchyRepository",
        lambda session: repo,
    )
    user = SpiceUserContext.model_validate(
        {"id": 42, "roles": [{"name": ROLE_SHASTIYA_KORMI, "suiteAccessName": "mob"}]}
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
        {"id": 42, "roles": [{"name": ROLE_SHASTIYA_KORMI, "suiteAccessName": "mob"}]}
    )
    with pytest.raises(AppError) as exc:
        await enforce_hierarchy_principal(MagicMock(), user)
    assert exc.value.code == ErrorCode.HIERARCHY_AUTH_FAILED.value
