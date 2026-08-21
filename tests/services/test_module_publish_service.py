"""Tests for ModulePublishService."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from mc_contracts.errors import ErrorCode
from platform_service.db.repositories.module_lifecycle_repository import (
    ModuleLifecycleError,
    ModuleNotFoundError,
)
from platform_service.services.module_publish_enrichment import ModulePublishEnrichmentError
from platform_service.services.module_publish_service import ModulePublishService
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.db.conftest import _make_family, _make_module
from tests.helpers.hierarchy_fixtures import PO_ID, seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]


class TestModulePublishService:
    @patch(
        "platform_service.services.module_publish_service.enrich_module_for_publish",
        new_callable=AsyncMock,
    )
    async def test_publishes_draft_module(self, mock_enrich: AsyncMock, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="draft")

        service = ModulePublishService(db_session)
        state = await service.publish(mod.id, reason="Testing service publish")

        mock_enrich.assert_awaited_once_with(db_session, mod.id)
        assert state.lifecycle_status == "published"
        assert state.activated_at is not None

        await db_session.refresh(mod)
        assert mod.lifecycle_status == "published"
        assert mod.published_at is not None
        assert fam.current_published_module_id == mod.id

    @patch(
        "platform_service.services.module_publish_service.enrich_module_for_publish",
        new_callable=AsyncMock,
    )
    async def test_publishes_with_published_by_user_id(
        self,
        mock_enrich: AsyncMock,
        db_session: AsyncSession,
    ) -> None:
        await seed_basic_hierarchy(db_session)
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="draft")

        service = ModulePublishService(db_session)
        await service.publish(mod.id, published_by_user_id=PO_ID, reason="Testing service publish")

        mock_enrich.assert_awaited_once()
        await db_session.refresh(mod)
        assert mod.published_by == PO_ID

    @patch(
        "platform_service.services.module_publish_service.enrich_module_for_publish",
        new_callable=AsyncMock,
    )
    async def test_raises_for_retired_module(
        self,
        mock_enrich: AsyncMock,
        db_session: AsyncSession,
    ) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="retired")

        service = ModulePublishService(db_session)
        with pytest.raises(ModuleLifecycleError):
            await service.publish(mod.id)

        mock_enrich.assert_not_awaited()

    @patch(
        "platform_service.services.module_publish_service.enrich_module_for_publish",
        new_callable=AsyncMock,
    )
    async def test_raises_for_missing_module(
        self,
        mock_enrich: AsyncMock,
        db_session: AsyncSession,
    ) -> None:
        service = ModulePublishService(db_session)
        with pytest.raises(ModuleNotFoundError):
            await service.publish(uuid4())

        mock_enrich.assert_not_awaited()

    @patch(
        "platform_service.services.module_publish_service.enrich_module_for_publish",
        new_callable=AsyncMock,
        side_effect=ModulePublishEnrichmentError(ErrorCode.EMBEDDING_FAILED, "embedding failed"),
    )
    async def test_blocks_publish_when_enrichment_fails(
        self,
        mock_enrich: AsyncMock,
        db_session: AsyncSession,
    ) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="draft")

        service = ModulePublishService(db_session)
        with pytest.raises(ModulePublishEnrichmentError):
            await service.publish(mod.id)

        mock_enrich.assert_awaited_once()
        await db_session.refresh(mod)
        assert mod.lifecycle_status == "draft"
