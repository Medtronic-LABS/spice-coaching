"""Unit tests for RagQueryRunner."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from eval.rag.corpus import CardCorpusDoc
from eval.rag.rag_dataset import RagGoldenRecord
from eval.rag.rag_runner import RagQueryRunner, resolve_cited_card_ids_to_modules
from mc_contracts.coaching import CoachingLocalRagRequest, CoachingRagResponse, RetrievedModuleHit

_MODULE_ID = UUID("11111111-1111-1111-1111-111111111111")
_CARD_ID = UUID("22222222-2222-2222-2222-222222222222")


def _sample_record() -> RagGoldenRecord:
    return RagGoldenRecord(
        id="Q001",
        category="Factual",
        language="bn",
        query="What is ANC?",
        expected_answer="Expected answer text",
        expected_module_ids=(_MODULE_ID,),
        is_out_of_scope=False,
        answerable="yes",
        expected_card_ids=(),
    )


@pytest.mark.asyncio
async def test_run_record_local_card_calls_local_query() -> None:
    mock_response = CoachingRagResponse(
        answer="Local card answer",
        retrieved_modules=[
            RetrievedModuleHit(
                module_id=_MODULE_ID,
                title={"bn": "Test"},
                domain="rmnch",
                cosine_distance=0.1,
            )
        ],
        source_documents=[],
        model="qwen-local",
        cited_module_ids=[_MODULE_ID],
        suggested_questions=["Next question?"],
        generation_context="CARD_BLOCK context",
    )

    mock_service = MagicMock()
    mock_service.local_query = AsyncMock(return_value=mock_response)
    mock_session = AsyncMock()

    with (
        patch("eval.rag.rag_runner.SessionLocal") as session_local,
        patch("eval.rag.rag_runner.CoachingRagService", return_value=mock_service),
        patch("eval.rag.rag_runner.AIRuntimeClient") as ai_client_cls,
    ):
        session_local.return_value.__aenter__.return_value = mock_session
        ai_client_cls.return_value.aclose = AsyncMock()

        runner = RagQueryRunner(local_card=True)
        result = await runner.run_record(_sample_record(), k=5)
        await runner.aclose()

    mock_service.local_query.assert_awaited_once()
    body = mock_service.local_query.await_args.args[0]
    assert isinstance(body, CoachingLocalRagRequest)
    assert body.question == "What is ANC?"
    assert body.response_language == "bn"
    assert body.include_generation_context is True
    mock_service.query.assert_not_called()

    assert result.answer == "Local card answer"
    assert result.model == "qwen-local"
    assert result.retrieved_module_ids == [str(_MODULE_ID)]
    assert result.cited_module_ids == [str(_MODULE_ID)]
    assert result.generation_context == "CARD_BLOCK context"
    assert result.error is None


def test_resolve_cited_card_ids_to_modules_maps_card_uuid_to_parent_module() -> None:
    cards_by_module = {
        _MODULE_ID: [
            CardCorpusDoc(
                module_id=_MODULE_ID,
                card_id=_CARD_ID,
                card_index=0,
                card_family_id=None,
                primary_title="Card title",
                title_en=None,
                title_bn="Card title",
                text="Card body",
            )
        ]
    }

    resolved = resolve_cited_card_ids_to_modules([str(_CARD_ID)], cards_by_module)

    assert resolved == [str(_MODULE_ID)]


@pytest.mark.asyncio
async def test_run_record_local_card_resolves_cited_card_ids() -> None:
    mock_response = CoachingRagResponse(
        answer="Local card answer",
        retrieved_modules=[
            RetrievedModuleHit(
                module_id=_MODULE_ID,
                title={"bn": "Test"},
                domain="rmnch",
                cosine_distance=0.1,
            )
        ],
        source_documents=[],
        model="qwen-local",
        cited_module_ids=[_CARD_ID],
        suggested_questions=[],
        generation_context="CARD_BLOCK context",
    )

    mock_service = MagicMock()
    mock_service.local_query = AsyncMock(return_value=mock_response)
    mock_session = AsyncMock()
    cards_by_module = {
        _MODULE_ID: [
            CardCorpusDoc(
                module_id=_MODULE_ID,
                card_id=_CARD_ID,
                card_index=0,
                card_family_id=None,
                primary_title="Card title",
                title_en=None,
                title_bn="Card title",
                text="Card body",
            )
        ]
    }

    with (
        patch("eval.rag.rag_runner.SessionLocal") as session_local,
        patch("eval.rag.rag_runner.CoachingRagService", return_value=mock_service),
        patch("eval.rag.rag_runner.AIRuntimeClient") as ai_client_cls,
    ):
        session_local.return_value.__aenter__.return_value = mock_session
        ai_client_cls.return_value.aclose = AsyncMock()

        runner = RagQueryRunner(local_card=True, cards_by_module=cards_by_module)
        result = await runner.run_record(_sample_record(), k=5)
        await runner.aclose()

    assert result.cited_module_ids == [str(_MODULE_ID)]
    assert result.citation_metrics["strict_citation_accuracy"] == 1.0
