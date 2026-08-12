"""Tests for ModulePublishService."""

from __future__ import annotations

from uuid import uuid4

import pytest
from platform_service.db.repositories.module_lifecycle_repository import (
    ModuleLifecycleError,
    ModuleNotFoundError,
)
from platform_service.services.module_publish_service import ModulePublishService
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.db.conftest import _make_family, _make_module

pytestmark = [requires_db, pytest.mark.asyncio]


class TestModulePublishService:
    async def test_publishes_draft_module(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="draft")

        service = ModulePublishService(db_session)
        state = await service.publish(mod.id, reason="Testing service publish")

        assert state.lifecycle_status == "published"
        assert state.first_activated_at is not None

        await db_session.refresh(mod)
        assert mod.lifecycle_status == "published"
        assert mod.published_at is not None
        assert fam.current_published_module_id == mod.id

    async def test_raises_for_retired_module(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="retired")

        service = ModulePublishService(db_session)
        with pytest.raises(ModuleLifecycleError):
            await service.publish(mod.id)

    async def test_raises_for_missing_module(self, db_session: AsyncSession) -> None:
        service = ModulePublishService(db_session)
        with pytest.raises(ModuleNotFoundError):
            await service.publish(uuid4())
