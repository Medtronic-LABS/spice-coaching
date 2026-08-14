"""Tests for synchronous module publish enrichment."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from mc_contracts.errors import ErrorCode
from platform_service.services.module_publish_enrichment import (
    ModulePublishEnrichmentError,
    enrich_module_for_publish,
    module_requires_metadata_regeneration,
)
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.db.conftest import _make_family, _make_module

pytestmark = [requires_db, pytest.mark.asyncio]


class TestModulePublishEnrichment:
    async def test_skips_when_all_artifacts_present(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(
            db_session,
            family=fam,
            lifecycle_status="draft",
            embedding=[0.1] * 768,
        )
        mod.search_metadata_jsonb = {"keywords": {"bn": ["kw"]}}
        await db_session.flush()
        cards = [{"title": {"bn": "Card"}, "search_metadata": {"keywords": {"bn": ["k"]}}}]

        with (
            patch(
                "platform_service.services.module_publish_enrichment._load_module_cards",
                new_callable=AsyncMock,
                return_value=(mod, cards),
            ),
            patch(
                "platform_service.services.module_publish_enrichment.generate_card_search_metadata_batch",
                new_callable=AsyncMock,
            ) as mock_card,
            patch(
                "platform_service.services.module_publish_enrichment.generate_search_metadata_for_module",
                new_callable=AsyncMock,
            ) as mock_module,
            patch(
                "platform_service.services.module_publish_enrichment.generate_embedding_for_module",
                new_callable=AsyncMock,
            ) as mock_embed,
        ):
            await enrich_module_for_publish(db_session, mod.id)

        mock_card.assert_not_awaited()
        mock_module.assert_not_awaited()
        mock_embed.assert_not_awaited()

    async def test_runs_missing_steps_in_order(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(
            db_session,
            family=fam,
            lifecycle_status="draft",
            embedding=None,
        )
        mod.search_metadata_jsonb = None
        await db_session.flush()

        call_order: list[str] = []

        async def _card(*_args, **_kwargs):
            call_order.append("card")
            return 1

        async def _module(*_args, **_kwargs):
            call_order.append("module")
            return True

        async def _embed(*_args, **_kwargs):
            call_order.append("embed")
            return True

        with (
            patch(
                "platform_service.services.module_publish_enrichment.generate_card_search_metadata_batch",
                side_effect=_card,
            ),
            patch(
                "platform_service.services.module_publish_enrichment.generate_search_metadata_for_module",
                side_effect=_module,
            ),
            patch(
                "platform_service.services.module_publish_enrichment.generate_embedding_for_module",
                side_effect=_embed,
            ),
            patch(
                "platform_service.services.module_publish_enrichment._load_module_cards",
                new_callable=AsyncMock,
            ) as mock_load,
        ):
            cards = [{"title": {"bn": "Card"}}]
            mock_load.side_effect = [
                (mod, cards),
                (mod, [{"title": {"bn": "Card"}, "search_metadata": {"keywords": {"bn": ["k"]}}}]),
            ]
            await enrich_module_for_publish(db_session, mod.id)

        assert call_order == ["card", "module", "embed"]

    async def test_raises_when_module_metadata_fails(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(
            db_session,
            family=fam,
            lifecycle_status="draft",
            embedding=None,
        )
        mod.search_metadata_jsonb = None
        await db_session.flush()

        with (
            patch(
                "platform_service.services.module_publish_enrichment.generate_card_search_metadata_batch",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "platform_service.services.module_publish_enrichment.generate_search_metadata_for_module",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "platform_service.services.module_publish_enrichment._load_module_cards",
                new_callable=AsyncMock,
                return_value=(mod, []),
            ),
        ):
            with pytest.raises(ModulePublishEnrichmentError) as exc_info:
                await enrich_module_for_publish(db_session, mod.id)

        assert exc_info.value.error_code == ErrorCode.SEARCH_METADATA_FAILED

    async def test_raises_for_missing_module(self, db_session: AsyncSession) -> None:
        with pytest.raises(ModulePublishEnrichmentError) as exc_info:
            await enrich_module_for_publish(db_session, uuid4())

        assert exc_info.value.error_code == ErrorCode.MODULE_NOT_FOUND

    async def test_merge_flag_detected(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(
            db_session,
            family=fam,
            lifecycle_status="draft",
            module_json={"cards": []},
        )
        mod.quality_flags_jsonb = {"flags": ["published_module_merged"]}
        await db_session.flush()

        assert module_requires_metadata_regeneration(mod) is True
