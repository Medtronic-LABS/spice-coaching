"""Tests for card-level embedding retrieval eval."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from eval.rag.card_embedding import CardEmbeddingHit, CardEmbeddingRetriever
from eval.rag.report import artifact_from_card_embedding_hits


def _hit(
    *,
    rank: int,
    module_id: UUID,
    card_id: UUID,
    distance: float,
) -> CardEmbeddingHit:
    return CardEmbeddingHit(
        rank=rank,
        module_id=module_id,
        card_id=card_id,
        card_index=rank - 1,
        primary_title=f"Card {rank}",
        title_en=f"Card {rank}",
        title_bn=None,
        cosine_distance=distance,
        text_preview="preview",
    )


class TestArtifactFromCardEmbeddingHits:
    def test_derives_module_metrics_from_unique_modules_in_rank_order(self) -> None:
        module_a = uuid4()
        module_b = uuid4()
        card_a1 = uuid4()
        card_a2 = uuid4()
        card_b1 = uuid4()
        gold_module = module_a
        gold_card = card_a1
        hits = [
            _hit(rank=1, module_id=module_a, card_id=card_a1, distance=0.1),
            _hit(rank=2, module_id=module_a, card_id=card_a2, distance=0.2),
            _hit(rank=3, module_id=module_b, card_id=card_b1, distance=0.3),
        ]

        artifact = artifact_from_card_embedding_hits(
            record_id="Q001",
            category="test",
            question="question",
            expected_module=None,
            is_answerable=True,
            relevant_module_ids=[gold_module],
            expected_card_ids=(gold_card,),
            hits=hits,
            k=3,
        )

        assert artifact.retrieved_module_ids == [str(module_a), str(module_b)]
        assert artifact.retrieval_scores == [0.1, 0.3]
        assert artifact.retrieval_metrics["hit_at_k"] == 1.0
        assert artifact.retrieved_card_ids == [str(card_a1), str(card_a2), str(card_b1)]
        assert artifact.card_retrieval_metrics["hit_at_k"] == 1.0
        assert artifact.card_retrieval_metrics["mrr"] == 1.0

    def test_omits_card_metrics_when_no_expected_cards(self) -> None:
        module_id = uuid4()
        card_id = uuid4()
        hits = [_hit(rank=1, module_id=module_id, card_id=card_id, distance=0.0)]

        artifact = artifact_from_card_embedding_hits(
            record_id="Q002",
            category="test",
            question="question",
            expected_module=None,
            is_answerable=True,
            relevant_module_ids=[module_id],
            expected_card_ids=(),
            hits=hits,
            k=1,
        )

        assert artifact.card_retrieval_metrics == {}
        assert artifact.retrieval_metrics["hit_at_k"] == 1.0


@pytest.mark.asyncio
class TestCardEmbeddingRetriever:
    async def test_search_returns_hydrated_hits(self) -> None:
        module_id = uuid4()
        card_id = uuid4()
        mock_client = AsyncMock()
        mock_client.embed.return_value = [[0.1] * 768]

        mock_store = AsyncMock()
        mock_store.search.return_value = [{"id": str(card_id), "distance": 0.05}]

        mock_card = MagicMock()
        mock_card.id = card_id
        mock_card.module_id = module_id
        mock_card.card_order = 0
        mock_card.title_localized = {"en": "Title"}

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_card]
        mock_session.execute.return_value = mock_result

        card_dict = {
            "id": str(card_id),
            "title": {"en": "Title"},
            "body": {"en": "Body"},
        }

        with (
            patch("eval.rag.card_embedding.SessionLocal") as session_local,
            patch("eval.rag.card_embedding.get_vector_store", return_value=mock_store),
            patch(
                "eval.rag.card_embedding.load_cards_by_module_ids",
                new=AsyncMock(return_value={module_id: [card_dict]}),
            ),
            patch(
                "eval.rag.card_embedding.assert_embedding_dimension",
                return_value=[0.1] * 768,
            ),
        ):
            session_local.return_value.__aenter__.return_value = mock_session
            retriever = CardEmbeddingRetriever(client=mock_client)
            hits = await retriever.search("query", k=1)

        assert len(hits) == 1
        assert hits[0].card_id == card_id
        assert hits[0].module_id == module_id
        assert hits[0].cosine_distance == 0.05
        mock_client.embed.assert_awaited_once_with(["query"], use_local=True)
        mock_store.search.assert_awaited_once()

    async def test_embedded_count_delegates_to_corpus_helper(self) -> None:
        with patch(
            "eval.rag.card_embedding.count_local_embedded_published_cards",
            new=AsyncMock(return_value=42),
        ):
            retriever = CardEmbeddingRetriever(client=AsyncMock())
            assert await retriever.embedded_count() == 42
