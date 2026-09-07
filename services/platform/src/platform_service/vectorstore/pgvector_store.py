"""Postgres / pgvector implementation of ``mc_foundation.vectorstore.VectorStore``.

Collections:

- ``modules`` — ``Module.embedding`` (cloud Gemini, production RAG)
- ``modules_local`` — ``Module.local_embedding`` (local EmbeddingGemma, eval)
- ``cards_local`` — ``ModuleCard.local_embedding`` (local EmbeddingGemma, card-level eval)

Search filter keys (interpreted only here — not in foundation):

- ``lifecycle_status`` (str) — defaults to ``\"published\"`` when omitted
- ``tenant_id`` (int) — optional tenant scope
- ``assignable_only`` (bool) — when true, restrict to training module families
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from mc_foundation.vectorstore import VectorMatch, VectorRecord
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.module import Module
from platform_service.db.models.module_card import ModuleCard
from platform_service.db.module_availability import is_training_module_family
from platform_service.db.tenant_scope import tenant_scope_filter

MODULES_COLLECTION = "modules"
MODULES_LOCAL_COLLECTION = "modules_local"
CARDS_LOCAL_COLLECTION = "cards_local"

_SUPPORTED_COLLECTIONS = frozenset({MODULES_COLLECTION, MODULES_LOCAL_COLLECTION, CARDS_LOCAL_COLLECTION})


class PgVectorStore:
    """Durable vectors co-located on Postgres via the pgvector extension."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, records: Sequence[VectorRecord]) -> None:
        for record in records:
            collection = record["collection"]
            if collection not in _SUPPORTED_COLLECTIONS:
                raise ValueError(f"unsupported vector collection: {collection!r}")
            vector = list(record["vector"])
            record_id = UUID(record["id"])
            if collection == CARDS_LOCAL_COLLECTION:
                card = await self._session.get(ModuleCard, record_id)
                if card is None:
                    continue
                card.local_embedding = vector
                continue
            module = await self._session.get(Module, record_id)
            if module is None:
                continue
            if collection == MODULES_COLLECTION:
                module.embedding = vector
            else:
                module.local_embedding = vector

    async def delete(self, collection: str, ids: Sequence[str]) -> None:
        if collection not in _SUPPORTED_COLLECTIONS:
            raise ValueError(f"unsupported vector collection: {collection!r}")
        if not ids:
            return
        record_ids = [UUID(item_id) for item_id in ids]
        if collection == CARDS_LOCAL_COLLECTION:
            await self._session.execute(
                update(ModuleCard).where(ModuleCard.id.in_(record_ids)).values(local_embedding=None)
            )
            return
        if collection == MODULES_COLLECTION:
            await self._session.execute(
                update(Module).where(Module.id.in_(record_ids)).values(embedding=None)
            )
        else:
            await self._session.execute(
                update(Module).where(Module.id.in_(record_ids)).values(local_embedding=None)
            )

    async def search(
        self,
        collection: str,
        query_vector: Sequence[float],
        *,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[VectorMatch]:
        if collection not in _SUPPORTED_COLLECTIONS:
            raise ValueError(f"unsupported vector collection: {collection!r}")
        if top_k <= 0:
            return []

        filters = filters or {}
        lifecycle_status = filters.get("lifecycle_status", "published")
        if not isinstance(lifecycle_status, str):
            raise ValueError("filters.lifecycle_status must be a str when provided")

        assignable_only = bool(filters.get("assignable_only", False))
        tenant_id = _parse_optional_tenant_id(filters.get("tenant_id"))

        if collection == CARDS_LOCAL_COLLECTION:
            return await self._search_cards_local(
                list(query_vector),
                top_k=top_k,
                lifecycle_status=lifecycle_status,
                assignable_only=assignable_only,
                tenant_id=tenant_id,
            )

        vector_column = Module.embedding if collection == MODULES_COLLECTION else Module.local_embedding
        distance = vector_column.cosine_distance(list(query_vector)).label("distance")
        stmt = (
            select(Module.id, distance)
            .where(vector_column.is_not(None), Module.lifecycle_status == lifecycle_status)
            .order_by(distance.asc())
            .limit(top_k)
        )
        if assignable_only:
            stmt = stmt.where(is_training_module_family())
        if tenant_id is not None:
            stmt = stmt.where(tenant_scope_filter(Module.tenant_id, tenant_id))

        rows = (await self._session.execute(stmt)).all()
        return [{"id": str(module_id), "distance": float(dist)} for module_id, dist in rows]

    async def _search_cards_local(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        lifecycle_status: str,
        assignable_only: bool,
        tenant_id: int | None,
    ) -> Sequence[VectorMatch]:
        distance = ModuleCard.local_embedding.cosine_distance(query_vector).label("distance")
        stmt = (
            select(ModuleCard.id, distance)
            .join(Module, ModuleCard.module_id == Module.id)
            .where(
                ModuleCard.local_embedding.is_not(None),
                Module.lifecycle_status == lifecycle_status,
            )
            .order_by(distance.asc())
            .limit(top_k)
        )
        if assignable_only:
            stmt = stmt.where(is_training_module_family())
        if tenant_id is not None:
            stmt = stmt.where(tenant_scope_filter(Module.tenant_id, tenant_id))

        rows = (await self._session.execute(stmt)).all()
        return [{"id": str(card_id), "distance": float(dist)} for card_id, dist in rows]


def _parse_optional_tenant_id(raw: object | None) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError("filters.tenant_id must be an int when provided")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        return int(raw)
    raise ValueError("filters.tenant_id must be an int or str when provided")
