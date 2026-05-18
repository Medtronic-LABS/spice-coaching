"""Post-publish embedding worker.

Per `docs/ARCHITECTURE_RESET.md`. Triggered on module publish (Stage 3
enqueues a Celery task per `module_id`). Reads the module's card text from
`module.module_json`, calls ai-runtime `/embed`, and writes the vector to
`module.embedding`.

The embedding is per-module (not per-card). It serves admin/web semantic
search inside this repo; the Android repo's runtime grounding flow uses it
via a standard fetch endpoint (added in step 11). Failure does not block
the module — the module remains readable in the dashboard via title and
full-text search until a later embedding run succeeds.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.base import SessionLocal
from platform_service.db.models.module import Module
from platform_service.integrations.ai_runtime_client import AIRuntimeClient

logger = logging.getLogger(__name__)


def _module_text_for_embedding(module: Module) -> str:
    """Concatenate the module's title and card text into a single embedding
    input. Order: title → each card's title + body + practice fields, in
    card order. Bangla canonical with English mirror folded in for cross-
    language search.
    """
    parts: list[str] = []
    if module.title_bn:
        parts.append(module.title_bn)
    if module.title_en:
        parts.append(module.title_en)
    if module.description_bn:
        parts.append(module.description_bn)
    cards = (module.module_json or {}).get("cards", [])
    for card in cards:
        if not isinstance(card, dict):
            continue
        for key in (
            "title_bn",
            "title_en",
            "body_bn",
            "body_en",
            "previous_practice_bn",
            "current_practice_bn",
            "rationale_for_change_bn",
            "next_action_bn",
        ):
            value = card.get(key)
            if value:
                parts.append(str(value))
    return "\n".join(parts)


async def generate_embedding_for_module(module_id: UUID) -> bool:
    """Generate and persist a per-module embedding. Returns True on success.

    The embedding column type is pgvector `vector(N)`. We pass a Python list
    of floats through SQLAlchemy as a bind parameter — pgvector accepts the
    list literal `[0.1, 0.2, …]` form when cast at the DB side.
    """
    async with SessionLocal() as session:
        module = await session.get(Module, module_id)
        if module is None:
            logger.warning("Embedding worker: module %s not found", module_id)
            return False
        text_input = _module_text_for_embedding(module)
        if not text_input.strip():
            logger.info("Embedding worker: module %s has no text; skipping", module_id)
            return False

        client = AIRuntimeClient()
        try:
            vectors = await client.embed([text_input])
        except Exception as exc:  # ai-runtime errors are not module-blocking
            logger.error("Embedding worker: ai-runtime error for module %s: %s", module_id, exc)
            return False
        if not vectors:
            logger.error("Embedding worker: empty embedding for module %s", module_id)
            return False

        await _persist_embedding(session, module_id, vectors[0])
        await session.commit()
        logger.info("Embedding worker: module %s embedded", module_id)
        return True


async def _persist_embedding(session: AsyncSession, module_id: UUID, vector: list[float]) -> None:
    """Write the embedding through the ORM. The Module.embedding column is
    pgvector-typed via `pgvector.sqlalchemy.Vector`, so a Python list[float]
    roundtrips cleanly without raw-SQL cast tricks."""
    module = await session.get(Module, module_id)
    if module is None:
        return
    module.embedding = list(vector)


__all__ = ["generate_embedding_for_module"]
