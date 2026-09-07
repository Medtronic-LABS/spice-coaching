#!/usr/bin/env python3
"""Add ``module_card.local_embedding`` and backfill cards via EmbeddingGemma.

Creates the ``local_embedding`` pgvector column when missing, then embeds each
published module card's search text through ai-runtime ``POST /internal/embed`` with
``use_local=true`` and persists the vector to ``module_card.local_embedding``.

Prerequisites (same env as platform service):

1. ``DATABASE_URL`` (and related platform config) so the script can read/write cards.
2. ``AI_RUNTIME_BASE_URL`` and ``AI_RUNTIME_TOKEN`` with ai-runtime reachable from this host.
3. ai-runtime configured for local embeddings (``LOCAL_EMBEDDING_*``, ``HUGGINGFACE_TOKEN``).

Usage:
    uv run python bin/backfill_module_card_local_embeddings.py [--dry-run] [--missing-only]
    uv run python bin/backfill_module_card_local_embeddings.py --module-id <uuid>

Examples:
    # List cards that would be embedded (no DDL, no ai-runtime calls)
    uv run python bin/backfill_module_card_local_embeddings.py --dry-run

    # Add column (if needed) and embed every card on published modules
    uv run python bin/backfill_module_card_local_embeddings.py

    # Only cards whose local_embedding column is still NULL
    uv run python bin/backfill_module_card_local_embeddings.py --missing-only
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
from platform_service.db.models.module_card import ModuleCard
from platform_service.db.tenant_scope import tenant_scope_filter
from platform_service.exceptions import EmbeddingDimensionError
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.localized import primary_text
from platform_service.services.card_normalisation import card_row_to_dict
from platform_service.services.embedding_vector import assert_embedding_dimension
from platform_service.services.module_search_text import card_text_for_search
from sqlalchemy import select, text

logger = logging.getLogger(__name__)

_EMBED_BATCH_SIZE = 32


@dataclass(frozen=True)
class CardTarget:
    card_id: UUID
    module_id: UUID
    title: str
    text_input: str


def _title_label(title_localized: dict[str, str] | None) -> str:
    return primary_text(title_localized) or ""


async def _local_embedding_column_exists() -> bool:
    check_sql = text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() "
        "AND table_name = 'module_card' AND column_name = 'local_embedding'"
    )
    async with SessionLocal() as session:
        return (await session.execute(check_sql)).scalar_one_or_none() is not None


async def _ensure_local_embedding_column(*, dry_run: bool) -> None:
    settings = get_settings()
    dim = settings.embedding_dimension
    if await _local_embedding_column_exists():
        logger.info("module_card.local_embedding column already present")
        return
    if dry_run:
        logger.info("dry run: would add module_card.local_embedding vector(%d)", dim)
        return
    async with SessionLocal() as session:
        await session.execute(text(f"ALTER TABLE module_card ADD COLUMN local_embedding vector({dim})"))
        await session.commit()
        logger.info("added module_card.local_embedding vector(%d)", dim)


async def _load_card_rows(
    session,
    *,
    tenant_id: int | None,
    module_id: UUID | None,
) -> list[ModuleCard]:
    stmt = (
        select(ModuleCard)
        .join(Module, ModuleCard.module_id == Module.id)
        .where(Module.lifecycle_status == "published")
        .order_by(
            ModuleCard.module_id.asc(),
            ModuleCard.card_order.asc(),
            ModuleCard.id.asc(),
        )
    )
    if module_id is not None:
        stmt = stmt.where(ModuleCard.module_id == module_id)
    if tenant_id is not None:
        stmt = stmt.where(tenant_scope_filter(Module.tenant_id, tenant_id))
    return list((await session.execute(stmt)).scalars().all())


async def _load_targets(
    *,
    missing_only: bool,
    tenant_id: int | None,
    module_id: UUID | None,
) -> list[CardTarget]:
    column_exists = await _local_embedding_column_exists()
    async with SessionLocal() as session:
        card_rows = await _load_card_rows(session, tenant_id=tenant_id, module_id=module_id)

        missing_ids: set[UUID] = set()
        if missing_only and column_exists and card_rows:
            rows = await session.execute(
                text(
                    "SELECT id FROM module_card "
                    "WHERE local_embedding IS NULL AND id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": [str(card.id) for card in card_rows]},
            )
            missing_ids = {row.id for row in rows}

        targets: list[CardTarget] = []
        for row in card_rows:
            if missing_only and column_exists and row.id not in missing_ids:
                continue
            card = card_row_to_dict(row)
            text_input = card_text_for_search(card)
            title = _title_label(row.title_localized)
            if not text_input.strip():
                logger.info("skip %s (%r): no embeddable text", row.id, title)
                continue
            targets.append(
                CardTarget(
                    card_id=row.id,
                    module_id=row.module_id,
                    title=title,
                    text_input=text_input,
                )
            )
        return targets


async def _persist_local_embedding(session, card_id: UUID, vector: list[float]) -> None:
    literal = "[" + ",".join(f"{value:.8g}" for value in vector) + "]"
    await session.execute(
        text("UPDATE module_card SET local_embedding = CAST(:embedding AS vector) WHERE id = :card_id"),
        {"embedding": literal, "card_id": card_id},
    )


async def _embed_batch(
    client: AIRuntimeClient,
    targets: list[CardTarget],
    *,
    expected_dim: int,
) -> list[tuple[CardTarget, list[float]]]:
    vectors = await client.embed([target.text_input for target in targets], use_local=True)
    if len(vectors) != len(targets):
        raise RuntimeError(f"ai-runtime returned {len(vectors)} vectors for {len(targets)} texts")
    out: list[tuple[CardTarget, list[float]]] = []
    for target, raw in zip(targets, vectors, strict=True):
        try:
            aligned = assert_embedding_dimension(raw, expected_dim=expected_dim)
        except EmbeddingDimensionError as exc:
            raise RuntimeError(f"dimension mismatch for card {target.card_id}: {exc}") from exc
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
            if found.lifecycle_status != "published":
                print(
                    f"Module {module_id} is not published (status={found.lifecycle_status!r}).",
                    file=sys.stderr,
                )
                return 1

    await _ensure_local_embedding_column(dry_run=dry_run)
    targets = await _load_targets(
        missing_only=missing_only,
        tenant_id=tenant_id,
        module_id=module_id,
    )
    if not targets:
        print("No cards matched — nothing to do.")
        return 0

    if dry_run:
        print(f"Dry run: would embed {len(targets)} card(s).")
        for target in targets:
            print(f"  {target.card_id}  module={target.module_id}  {target.title!r}")
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
                    await _persist_local_embedding(session, target.card_id, vector)
                    print(f"embedded {target.card_id}  module={target.module_id}  {target.title!r}")
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
        help="Print card IDs and titles without DDL or ai-runtime calls",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only cards whose local_embedding column is NULL",
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
        help="Backfill cards for one published module by ID",
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
