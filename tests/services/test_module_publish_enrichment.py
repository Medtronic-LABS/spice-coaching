"""Tests for synchronous module publish enrichment."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
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

_SETTINGS = SimpleNamespace(
    post_publish_search_metadata_enabled=True,
    post_publish_card_search_metadata_enabled=True,
    publish_enrichment_parallel_metadata_enabled=True,
)


def _settings(**overrides: object) -> SimpleNamespace:
    return SimpleNamespace(**{**_SETTINGS.__dict__, **overrides})


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
                "platform_service.services.module_publish_enrichment.get_settings",
                return_value=_settings(),
            ),
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

    async def test_sequential_runs_missing_steps_in_order(self, db_session: AsyncSession) -> None:
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
                "platform_service.services.module_publish_enrichment.get_settings",
                return_value=_settings(publish_enrichment_parallel_metadata_enabled=False),
            ),
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

    async def test_parallel_runs_metadata_before_embed(self, db_session: AsyncSession) -> None:
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
        card_started = asyncio.Event()
        module_started = asyncio.Event()

        async def _card(*_args, **_kwargs):
            call_order.append("card_start")
            card_started.set()
            await module_started.wait()
            call_order.append("card_done")
            return 1

        async def _module(*_args, **_kwargs):
            call_order.append("module_start")
            module_started.set()
            await card_started.wait()
            call_order.append("module_done")
            return True

        async def _embed(*_args, **_kwargs):
            call_order.append("embed")
            return True

        with (
            patch(
                "platform_service.services.module_publish_enrichment.get_settings",
                return_value=_settings(publish_enrichment_parallel_metadata_enabled=True),
            ),
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
            enriched_cards = [{"title": {"bn": "Card"}, "search_metadata": {"keywords": {"bn": ["k"]}}}]
            mod_after = MagicMock()
            mod_after.id = mod.id
            mod_after.search_metadata_jsonb = {"keywords": {"bn": ["kw"]}}
            mod_after.embedding = None
            mock_load.side_effect = [
                (mod, cards),
                (mod_after, enriched_cards),
            ]
            await enrich_module_for_publish(db_session, mod.id)

        assert "card_start" in call_order
        assert "module_start" in call_order
        assert call_order.index("card_done") < call_order.index("embed")
        assert call_order.index("module_done") < call_order.index("embed")
        assert call_order[-1] == "embed"

    async def test_parallel_module_metadata_failure_skips_embed(self, db_session: AsyncSession) -> None:
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
                "platform_service.services.module_publish_enrichment.get_settings",
                return_value=_settings(publish_enrichment_parallel_metadata_enabled=True),
            ),
            patch(
                "platform_service.services.module_publish_enrichment.generate_card_search_metadata_batch",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "platform_service.services.module_publish_enrichment.generate_search_metadata_for_module",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "platform_service.services.module_publish_enrichment.generate_embedding_for_module",
                new_callable=AsyncMock,
            ) as mock_embed,
            patch(
                "platform_service.services.module_publish_enrichment._load_module_cards",
                new_callable=AsyncMock,
            ) as mock_load,
        ):
            cards = [{"title": {"bn": "Card"}}]
            enriched_cards = [{"title": {"bn": "Card"}, "search_metadata": {"keywords": {"bn": ["k"]}}}]
            mock_load.side_effect = [
                (mod, cards),
                (mod, enriched_cards),
            ]
            with pytest.raises(ModulePublishEnrichmentError) as exc_info:
                await enrich_module_for_publish(db_session, mod.id)

        assert exc_info.value.error_code == ErrorCode.SEARCH_METADATA_FAILED
        mock_embed.assert_not_awaited()

    async def test_parallel_card_metadata_failure_skips_embed(self, db_session: AsyncSession) -> None:
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
                "platform_service.services.module_publish_enrichment.get_settings",
                return_value=_settings(publish_enrichment_parallel_metadata_enabled=True),
            ),
            patch(
                "platform_service.services.module_publish_enrichment.generate_card_search_metadata_batch",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "platform_service.services.module_publish_enrichment.generate_search_metadata_for_module",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "platform_service.services.module_publish_enrichment.generate_embedding_for_module",
                new_callable=AsyncMock,
            ) as mock_embed,
            patch(
                "platform_service.services.module_publish_enrichment._load_module_cards",
                new_callable=AsyncMock,
            ) as mock_load,
        ):
            cards = [{"title": {"bn": "Card"}}]
            mock_load.side_effect = [
                (mod, cards),
                (mod, cards),  # still missing card metadata after worker
            ]
            with pytest.raises(ModulePublishEnrichmentError) as exc_info:
                await enrich_module_for_publish(db_session, mod.id)

        assert exc_info.value.error_code == ErrorCode.CARD_SEARCH_METADATA_FAILED
        mock_embed.assert_not_awaited()

    async def test_only_embedding_when_metadata_present(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(
            db_session,
            family=fam,
            lifecycle_status="draft",
            embedding=None,
        )
        mod.search_metadata_jsonb = {"keywords": {"bn": ["kw"]}}
        await db_session.flush()
        cards = [{"title": {"bn": "Card"}, "search_metadata": {"keywords": {"bn": ["k"]}}}]

        with (
            patch(
                "platform_service.services.module_publish_enrichment.get_settings",
                return_value=_settings(),
            ),
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
                return_value=True,
            ) as mock_embed,
        ):
            await enrich_module_for_publish(db_session, mod.id)

        mock_card.assert_not_awaited()
        mock_module.assert_not_awaited()
        mock_embed.assert_awaited_once()

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
                "platform_service.services.module_publish_enrichment.get_settings",
                return_value=_settings(),
            ),
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

    async def test_merge_flag_forces_card_metadata(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(
            db_session,
            family=fam,
            lifecycle_status="draft",
            embedding=[0.1] * 768,
        )
        mod.search_metadata_jsonb = {"keywords": {"bn": ["kw"]}}
        mod.quality_flags_jsonb = {"flags": ["published_module_merged"]}
        await db_session.flush()
        cards = [{"title": {"bn": "Card"}, "search_metadata": {"keywords": {"bn": ["k"]}}}]

        with (
            patch(
                "platform_service.services.module_publish_enrichment.get_settings",
                return_value=_settings(),
            ),
            patch(
                "platform_service.services.module_publish_enrichment._load_module_cards",
                new_callable=AsyncMock,
            ) as mock_load,
            patch(
                "platform_service.services.module_publish_enrichment.generate_card_search_metadata_batch",
                new_callable=AsyncMock,
                return_value=1,
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
            mock_load.side_effect = [
                (mod, cards),
                (mod, cards),
            ]
            await enrich_module_for_publish(db_session, mod.id)

        mock_card.assert_awaited_once()
        assert mock_card.await_args.kwargs.get("force") is True
        mock_module.assert_not_awaited()
        mock_embed.assert_not_awaited()
