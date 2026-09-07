"""Card-level embedding retrieval via ai-runtime + pgvector cosine distance search."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from platform_service.config import get_settings
from platform_service.db.base import SessionLocal
from platform_service.db.models.module_card import ModuleCard
from platform_service.exceptions import EmbeddingDimensionError
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.services.embedding_vector import assert_embedding_dimension
from platform_service.services.module_search_text import card_text_for_search
from platform_service.vectorstore import CARDS_LOCAL_COLLECTION, get_vector_store
from sqlalchemy import select

from eval.rag.corpus import (
    _card_title_parts,
    _title_parts_from_localized,
    count_local_embedded_published_cards,
    load_cards_by_module_ids,
)


@dataclass(frozen=True)
class CardEmbeddingHit:
    rank: int
    module_id: UUID
    card_id: UUID
    card_index: int
    primary_title: str | None
    title_en: str | None
    title_bn: str | None
    cosine_distance: float
    text_preview: str


class CardEmbeddingRetriever:
    """Embed queries via ai-runtime and search published cards by cosine distance."""

    def __init__(
        self,
        *,
        tenant_id: int | None = None,
        client: AIRuntimeClient | None = None,
        base_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._settings = get_settings()
        self._client = client or AIRuntimeClient(base_url=base_url, token=token)
        self._owns_client = client is None
        self._embedded_count: int | None = None

    async def embedded_count(self) -> int:
        if self._embedded_count is None:
            self._embedded_count = await count_local_embedded_published_cards(tenant_id=self._tenant_id)
        return self._embedded_count

    async def search(self, query: str, *, k: int) -> list[CardEmbeddingHit]:
        vectors = await self._client.embed([query], use_local=True)
        if not vectors:
            raise RuntimeError("ai-runtime returned no embedding for query")

        try:
            vec = assert_embedding_dimension(vectors[0], expected_dim=self._settings.embedding_dimension)
        except EmbeddingDimensionError as exc:
            raise RuntimeError(str(exc)) from exc

        async with SessionLocal() as session:
            filters: dict[str, object] = {"lifecycle_status": "published"}
            if self._tenant_id is not None:
                filters["tenant_id"] = self._tenant_id
            store = get_vector_store(session)
            matches = await store.search(
                CARDS_LOCAL_COLLECTION,
                vec,
                top_k=k,
                filters=filters,
            )
            ordered_ids = [UUID(match["id"]) for match in matches]
            if not ordered_ids:
                return []

            rows = (
                (await session.execute(select(ModuleCard).where(ModuleCard.id.in_(ordered_ids))))
                .scalars()
                .all()
            )
            cards_by_id = {card.id: card for card in rows}
            module_ids = list({card.module_id for card in rows})
            cards_by_module = await load_cards_by_module_ids(module_ids)
            card_index_by_id = {
                UUID(str(card["id"])): index
                for module_cards in cards_by_module.values()
                for index, card in enumerate(module_cards)
            }

        hits: list[CardEmbeddingHit] = []
        for rank, (card_id, match) in enumerate(
            zip(ordered_ids, matches, strict=True),
            start=1,
        ):
            card = cards_by_id.get(card_id)
            if card is None:
                continue
            card_dict = next(
                (row for row in cards_by_module.get(card.module_id, []) if UUID(str(row["id"])) == card.id),
                None,
            )
            if card_dict is not None:
                preview = card_text_for_search(card_dict)[:120].replace("\n", " ")
                primary_title, title_en, title_bn = _card_title_parts(card_dict)
            else:
                preview = ""
                primary_title, title_en, title_bn = _title_parts_from_localized(card.title_localized)
            hits.append(
                CardEmbeddingHit(
                    rank=rank,
                    module_id=card.module_id,
                    card_id=card.id,
                    card_index=card_index_by_id.get(card.id, card.card_order),
                    primary_title=primary_title,
                    title_en=title_en,
                    title_bn=title_bn,
                    cosine_distance=float(match["distance"]),
                    text_preview=preview,
                )
            )
        return hits

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
