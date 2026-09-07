#!/usr/bin/env python3
"""Add ``module.local_embedding`` and backfill published modules via EmbeddingGemma.

Creates the ``local_embedding`` pgvector column when missing, then embeds each
published module's search text through ai-runtime ``POST /internal/embed`` with
``use_local=true`` and persists the vector to ``module.local_embedding``.

Prerequisites (same env as platform service):

1. ``DATABASE_URL`` (and related platform config) so the script can read/write modules.
2. ``AI_RUNTIME_BASE_URL`` and ``AI_RUNTIME_TOKEN`` with ai-runtime reachable from this host.
3. ai-runtime configured for local embeddings (``LOCAL_EMBEDDING_*``, ``HUGGINGFACE_TOKEN``).

Usage:
    uv run python bin/backfill_module_local_embeddings.py [--dry-run] [--missing-only]
    uv run python bin/backfill_module_local_embeddings.py --module-id <uuid>

Examples:
    # List published modules that would be embedded (no DDL, no ai-runtime calls)
    uv run python bin/backfill_module_local_embeddings.py --dry-run

    # Add column (if needed) and embed every published module
    uv run python bin/backfill_module_local_embeddings.py

    # Only modules whose local_embedding column is still NULL
    uv run python bin/backfill_module_local_embeddings.py --missing-only
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from uuid import UUID

from platform_service.config import get_settings
from platform_service.db.base import SessionLocal
from platform_service.db.models.module import Module
from platform_service.db.repositories.module_read_repository import ModuleReadRepository
from platform_service.exceptions import EmbeddingDimensionError
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.localized import primary_text
from platform_service.services.card_normalisation import card_row_to_dict
from platform_service.services.embedding_vector import assert_embedding_dimension
from platform_service.services.module_search_text import module_text_for_search
from sqlalchemy import text

logger = logging.getLogger(__name__)

_EMBED_BATCH_SIZE = 32


@dataclass(frozen=True)
class ModuleTarget:
    module_id: UUID
    title: str
    text_input: str


def _title_label(title_localized: dict[str, str] | None) -> str:
    return primary_text(title_localized) or ""


async def _local_embedding_column_exists() -> bool:
    check_sql = text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() "
        "AND table_name = 'module' AND column_name = 'local_embedding'"
    )
    async with SessionLocal() as session:
        return (await session.execute(check_sql)).scalar_one_or_none() is not None


async def _ensure_local_embedding_column(*, dry_run: bool) -> None:
    settings = get_settings()
    dim = settings.embedding_dimension
    if await _local_embedding_column_exists():
        logger.info("module.local_embedding column already present")
        return
    if dry_run:
        logger.info("dry run: would add module.local_embedding vector(%d)", dim)
        return
    async with SessionLocal() as session:
        await session.execute(text(f"ALTER TABLE module ADD COLUMN local_embedding vector({dim})"))
        await session.commit()
        logger.info("added module.local_embedding vector(%d)", dim)


async def _load_targets(
    *,
    missing_only: bool,
    tenant_id: int | None,
    module_id: UUID | None,
) -> list[ModuleTarget]:
    column_exists = await _local_embedding_column_exists()
    async with SessionLocal() as session:
        if module_id is not None:
            module = await session.get(Module, module_id)
            modules = [module] if module is not None else []
        else:
            repo = ModuleReadRepository(session)
            modules = await repo.list_modules(status="published", limit=10_000, tenant_id=tenant_id)

        missing_ids: set[UUID] = set()
        if missing_only and column_exists and modules:
            rows = await session.execute(
                text(
                    "SELECT id FROM module WHERE local_embedding IS NULL AND id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": [str(module.id) for module in modules if module is not None]},
            )
            missing_ids = {row.id for row in rows}

        targets: list[ModuleTarget] = []
        for module in modules:
            if module is None:
                continue
            if missing_only and column_exists and module.id not in missing_ids:
                continue
            card_rows = await ModuleReadRepository(session).list_cards(module.id)
            cards = [card_row_to_dict(row) for row in card_rows]
            text_input = module_text_for_search(module, cards=cards)
            if not text_input.strip():
                logger.info(
                    "skip %s (%r): no embeddable text", module.id, _title_label(module.title_localized)
                )
                continue
            targets.append(
                ModuleTarget(
                    module_id=module.id,
                    title=_title_label(module.title_localized),
                    text_input=text_input,
                )
            )
        return targets


async def _persist_local_embedding(session, module_id: UUID, vector: list[float]) -> None:
    literal = "[" + ",".join(f"{value:.8g}" for value in vector) + "]"
    await session.execute(
        text("UPDATE module SET local_embedding = CAST(:embedding AS vector) WHERE id = :module_id"),
        {"embedding": literal, "module_id": module_id},
    )


async def _embed_batch(
    client: AIRuntimeClient,
    targets: list[ModuleTarget],
    *,
    expected_dim: int,
) -> list[tuple[ModuleTarget, list[float]]]:
    vectors = await client.embed([target.text_input for target in targets], use_local=True)
    if len(vectors) != len(targets):
        raise RuntimeError(f"ai-runtime returned {len(vectors)} vectors for {len(targets)} texts")
    out: list[tuple[ModuleTarget, list[float]]] = []
    for target, raw in zip(targets, vectors, strict=True):
        try:
            aligned = assert_embedding_dimension(raw, expected_dim=expected_dim)
        except EmbeddingDimensionError as exc:
            raise RuntimeError(f"dimension mismatch for module {target.module_id}: {exc}") from exc
        out.append((target, aligned))
    return out


async def _run(
    *,
    dry_run: bool,
    missing_only: bool,
    tenant_id: int | None,
    module_id: UUID | None,
    batch_size: int,
) -> int:
    if module_id is not None:
        async with SessionLocal() as session:
            found = await session.get(Module, module_id)
            if found is None:
                print(f"Module {module_id} not found.", file=sys.stderr)
                return 1

    await _ensure_local_embedding_column(dry_run=dry_run)
    targets = await _load_targets(
        missing_only=missing_only,
        tenant_id=tenant_id,
        module_id=module_id,
    )
    if not targets:
        print("No modules matched — nothing to do.")
        return 0

    if dry_run:
        print(f"Dry run: would embed {len(targets)} module(s).")
        for target in targets:
            print(f"  {target.module_id}  {target.title!r}")
        return 0

    settings = get_settings()
    client = AIRuntimeClient()
    embedded = 0
    try:
        for start in range(0, len(targets), batch_size):
            batch = targets[start : start + batch_size]
            pairs = await _embed_batch(client, batch, expected_dim=settings.embedding_dimension)
            async with SessionLocal() as session:
                for target, vector in pairs:
                    await _persist_local_embedding(session, target.module_id, vector)
                    print(f"embedded {target.module_id}  {target.title!r}")
                    embedded += 1
                await session.commit()
    finally:
        await client.aclose()

    print(f"Done. embedded={embedded}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print module IDs and titles without DDL or ai-runtime calls",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only modules whose local_embedding column is NULL",
    )
    parser.add_argument(
        "--tenant-id",
        type=int,
        default=None,
        help="Restrict bulk backfill to one tenant (SPICE bigint)",
    )
    parser.add_argument(
        "--module-id",
        type=UUID,
        default=None,
        help="Backfill a single module by ID (any lifecycle status)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_EMBED_BATCH_SIZE,
        help=f"Texts per ai-runtime embed request (max 100, default {_EMBED_BATCH_SIZE})",
    )
    args = parser.parse_args()
    if args.batch_size <= 0 or args.batch_size > 100:
        parser.error("--batch-size must be between 1 and 100")
    logging.basicConfig(level=logging.INFO)
    return asyncio.run(
        _run(
            dry_run=args.dry_run,
            missing_only=args.missing_only,
            tenant_id=args.tenant_id,
            module_id=args.module_id,
            batch_size=args.batch_size,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
