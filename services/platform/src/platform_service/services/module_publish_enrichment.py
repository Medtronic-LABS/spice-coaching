"""Synchronous metadata and embedding enrichment at admin module publish."""

from __future__ import annotations

import asyncio
import logging
import time
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

logger = logging.getLogger(__name__)


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


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0


async def _load_module_cards(
    session: AsyncSession,
    module_id: UUID,
) -> tuple[Module | None, list[dict[str, Any]]]:
    module = await session.get(Module, module_id)
    if module is None:
        return None, []
    card_rows = await ModuleReadRepository(session).list_cards(module_id)
    return module, [card_row_to_dict(row) for row in card_rows]


async def _reload_after_workers(
    session: AsyncSession,
    module_id: UUID,
) -> tuple[Module, list[dict[str, Any]]]:
    """Refresh request session after workers committed via their own sessions."""
    session.expire_all()
    module, cards = await _load_module_cards(session, module_id)
    if module is None:
        raise ModulePublishEnrichmentError(
            ErrorCode.MODULE_NOT_FOUND,
            f"module {module_id} not found",
        )
    return module, cards


def _assert_card_metadata_complete(cards: list[dict[str, Any]]) -> None:
    if cards and _cards_missing_metadata(cards):
        raise ModulePublishEnrichmentError(
            ErrorCode.CARD_SEARCH_METADATA_FAILED,
            "card search metadata generation failed or incomplete",
        )


def _assert_module_metadata_written(written: bool) -> None:
    if not written:
        raise ModulePublishEnrichmentError(
            ErrorCode.SEARCH_METADATA_FAILED,
            "module search metadata generation failed",
        )


async def _generate_card_metadata(module_id: UUID, *, force: bool) -> float:
    started = time.perf_counter()
    await generate_card_search_metadata_batch(
        module_id,
        force=force,
        chain_downstream=False,
    )
    return _elapsed_ms(started)


async def _generate_module_metadata(module_id: UUID) -> tuple[bool, float]:
    started = time.perf_counter()
    written = await generate_search_metadata_for_module(
        module_id,
        chain_downstream=False,
    )
    return written, _elapsed_ms(started)


async def _generate_embedding(module_id: UUID) -> float:
    started = time.perf_counter()
    embedded = await generate_embedding_for_module(module_id, step_id=None)
    elapsed = _elapsed_ms(started)
    if not embedded:
        raise ModulePublishEnrichmentError(
            ErrorCode.EMBEDDING_FAILED,
            "module embedding generation failed",
        )
    return elapsed


def _log_enrichment_timings(
    *,
    module_id: UUID,
    parallel: bool,
    card_ms: float | None,
    module_ms: float | None,
    embed_ms: float | None,
    metadata_wall_ms: float | None,
    total_enrich_ms: float,
) -> None:
    logger.info(
        "publish enrichment timings module_id=%s parallel=%s card_ms=%s module_ms=%s "
        "embed_ms=%s metadata_wall_ms=%s total_enrich_ms=%.1f",
        module_id,
        parallel,
        f"{card_ms:.1f}" if card_ms is not None else None,
        f"{module_ms:.1f}" if module_ms is not None else None,
        f"{embed_ms:.1f}" if embed_ms is not None else None,
        f"{metadata_wall_ms:.1f}" if metadata_wall_ms is not None else None,
        total_enrich_ms,
    )


async def enrich_module_for_publish(session: AsyncSession, module_id: UUID) -> None:
    """Generate missing card/module search metadata and embedding before publish.

    When ``publish_enrichment_parallel_metadata_enabled`` is True and both
    metadata steps are needed, card and module search-metadata LLM calls run
    concurrently; embedding always runs after metadata so vector text includes
    both layers. Set the flag False to restore strict sequential metadata.
    """
    total_started = time.perf_counter()
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

    parallel_flag = settings.publish_enrichment_parallel_metadata_enabled
    use_parallel = parallel_flag and need_card_metadata and need_module_metadata

    card_ms: float | None = None
    module_ms: float | None = None
    embed_ms: float | None = None
    metadata_wall_ms: float | None = None

    try:
        if use_parallel:
            metadata_started = time.perf_counter()
            card_result, module_result = await asyncio.gather(
                _generate_card_metadata(module_id, force=force_card_metadata),
                _generate_module_metadata(module_id),
                return_exceptions=True,
            )
            metadata_wall_ms = _elapsed_ms(metadata_started)

            if isinstance(card_result, BaseException):
                raise card_result
            if isinstance(module_result, BaseException):
                raise module_result

            card_ms = card_result
            metadata_written, module_ms = module_result

            module, cards = await _reload_after_workers(session, module_id)
            _assert_card_metadata_complete(cards)
            _assert_module_metadata_written(metadata_written)
            if not _has_module_metadata(module):
                raise ModulePublishEnrichmentError(
                    ErrorCode.SEARCH_METADATA_FAILED,
                    "module search metadata generation failed",
                )
        else:
            if need_card_metadata:
                card_ms = await _generate_card_metadata(module_id, force=force_card_metadata)
                module, cards = await _reload_after_workers(session, module_id)
                _assert_card_metadata_complete(cards)

            if need_module_metadata:
                metadata_written, module_ms = await _generate_module_metadata(module_id)
                _assert_module_metadata_written(metadata_written)

            if need_card_metadata or need_module_metadata:
                metadata_wall_ms = (card_ms or 0.0) + (module_ms or 0.0)

        if need_embedding:
            embed_ms = await _generate_embedding(module_id)
    finally:
        _log_enrichment_timings(
            module_id=module_id,
            parallel=use_parallel,
            card_ms=card_ms,
            module_ms=module_ms,
            embed_ms=embed_ms,
            metadata_wall_ms=metadata_wall_ms,
            total_enrich_ms=_elapsed_ms(total_started),
        )


__all__ = [
    "ModulePublishEnrichmentError",
    "enrich_module_for_publish",
    "module_requires_metadata_regeneration",
]
