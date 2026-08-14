"""Synchronous metadata and embedding enrichment at admin module publish."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from mc_contracts.errors import ErrorCode
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import get_settings
from platform_service.db.models.module import Module
from platform_service.db.repositories.module_read_repository import ModuleReadRepository
from platform_service.services.card_normalisation import card_row_to_dict
from platform_service.workers.card_search_metadata_worker import generate_card_search_metadata_batch
from platform_service.workers.embedding_worker import generate_embedding_for_module
from platform_service.workers.search_metadata_worker import generate_search_metadata_for_module

_PUBLISHED_MODULE_MERGED_FLAG = "published_module_merged"


class ModulePublishEnrichmentError(Exception):
    """Raised when publish-time enrichment fails and publish must be blocked."""

    def __init__(self, error_code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def module_requires_metadata_regeneration(module: Module) -> bool:
    flags = (module.quality_flags_jsonb or {}).get("flags") or []
    return _PUBLISHED_MODULE_MERGED_FLAG in flags


def _has_module_metadata(module: Module) -> bool:
    return bool(module.search_metadata_jsonb)


def _cards_missing_metadata(cards: list[dict[str, Any]]) -> bool:
    if not cards:
        return False
    return any(not card.get("search_metadata") for card in cards)


async def _load_module_cards(
    session: AsyncSession,
    module_id: UUID,
) -> tuple[Module | None, list[dict[str, Any]]]:
    module = await session.get(Module, module_id)
    if module is None:
        return None, []
    card_rows = await ModuleReadRepository(session).list_cards(module_id)
    return module, [card_row_to_dict(row) for row in card_rows]


async def enrich_module_for_publish(session: AsyncSession, module_id: UUID) -> None:
    """Generate missing card/module search metadata and embedding before publish."""
    settings = get_settings()
    module, cards = await _load_module_cards(session, module_id)
    if module is None:
        raise ModulePublishEnrichmentError(
            ErrorCode.MODULE_NOT_FOUND,
            f"module {module_id} not found",
        )

    force_card_metadata = module_requires_metadata_regeneration(module)
    card_metadata_enabled = (
        settings.post_publish_search_metadata_enabled and settings.post_publish_card_search_metadata_enabled
    )
    need_card_metadata = card_metadata_enabled and (force_card_metadata or _cards_missing_metadata(cards))
    need_module_metadata = settings.post_publish_search_metadata_enabled and not _has_module_metadata(module)
    need_embedding = module.embedding is None

    if not need_card_metadata and not need_module_metadata and not need_embedding:
        return

    if need_card_metadata:
        await generate_card_search_metadata_batch(
            module_id,
            force=force_card_metadata,
            chain_downstream=False,
        )
        module, cards = await _load_module_cards(session, module_id)
        if module is None:
            raise ModulePublishEnrichmentError(
                ErrorCode.MODULE_NOT_FOUND,
                f"module {module_id} not found",
            )
        if cards and _cards_missing_metadata(cards):
            raise ModulePublishEnrichmentError(
                ErrorCode.CARD_SEARCH_METADATA_FAILED,
                "card search metadata generation failed or incomplete",
            )

    if need_module_metadata:
        metadata_written = await generate_search_metadata_for_module(
            module_id,
            chain_downstream=False,
        )
        if not metadata_written:
            raise ModulePublishEnrichmentError(
                ErrorCode.SEARCH_METADATA_FAILED,
                "module search metadata generation failed",
            )

    if need_embedding:
        embedded = await generate_embedding_for_module(module_id, step_id=None)
        if not embedded:
            raise ModulePublishEnrichmentError(
                ErrorCode.EMBEDDING_FAILED,
                "module embedding generation failed",
            )


__all__ = [
    "ModulePublishEnrichmentError",
    "enrich_module_for_publish",
    "module_requires_metadata_regeneration",
]
