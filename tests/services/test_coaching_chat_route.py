"""Unit tests for coaching chat router parse + RAG early-exit wiring."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from mc_contracts.coaching import CoachingLocalRagRequest, CoachingRagRequest
from mc_contracts.enums import GenerationType
from mc_contracts.internal_ai import InferenceResponse
from platform_service.config import Settings
from platform_service.services.coaching_chat_router import (
    CoachingChatRouter,
    parse_chat_route_payload,
)
from platform_service.services.coaching_rag_errors import CoachingRagError
from platform_service.services.coaching_rag_service import (
    CoachingRagService,
    coaching_rag_response_locales,
    resolve_response_language,
)
from platform_service.services.prompt_registry import COACHING_LOCAL_CARD_CHAT_ROUTE_TEMPLATE_ID
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("mock_prompt_templates")


def _route_resp(
    parsed_json: Any = None,
    *,
    raw_text: str = "",
    error: str | None = None,
    model: str = "gemini-route",
) -> InferenceResponse:
    return InferenceResponse(
        request_id="r-route",
        generation_type=GenerationType.COACHING_CHAT_ROUTE,
        provider="google",
        model=model,
        max_tokens=512,
        temperature=0.1,
        raw_text=raw_text,
        parsed_json=parsed_json,
        latency_ms=50,
        error=error,
    )


def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "coaching_rag_module_limit": 5,
        "coaching_rag_presigned_url_ttl_seconds": 3600,
        "coaching_rag_context_max_chars": 28_000,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _rag_svc(*, ai: Any) -> CoachingRagService:
    session = MagicMock(spec=AsyncSession)
    storage = MagicMock()
    return CoachingRagService(session, ai, storage, settings=_settings())


# ─── parse_chat_route_payload ─────────────────────────────────────────────


def test_parse_chitchat_high_confidence_early_returns() -> None:
    result = parse_chat_route_payload(
        {
            "intent": "chitchat",
            "confidence": "high",
            "answer": "Hello! How can I help with your training?",
            "suggested_questions": ["What is ANC?", "How to refer?"],
        },
        model="m1",
    )
    assert result is not None
    assert result.should_early_return is True
    assert result.intent == "chitchat"
    assert result.model == "m1"
    assert len(result.suggested_questions) == 2


def test_parse_chitchat_low_confidence_falls_through() -> None:
    result = parse_chat_route_payload(
        {
            "intent": "chitchat",
            "confidence": "low",
            "answer": "Hi",
        }
    )
    assert result is not None
    assert result.should_early_return is False


def test_parse_crisis_early_returns_without_suggestions() -> None:
    result = parse_chat_route_payload(
        {
            "intent": "crisis",
            "confidence": "low",
            "answer": "Please seek local emergency help now.",
            "suggested_questions": ["ignored"],
        }
    )
    assert result is not None
    assert result.should_early_return is True
    assert result.suggested_questions == []


def test_parse_crisis_empty_answer_returns_none() -> None:
    assert parse_chat_route_payload({"intent": "crisis", "confidence": "high", "answer": ""}) is None


def test_parse_coaching_question_never_early_returns() -> None:
    result = parse_chat_route_payload(
        {
            "intent": "coaching_question",
            "confidence": "high",
            "answer": "",
        }
    )
    assert result is not None
    assert result.should_early_return is False


def test_parse_invalid_intent_returns_none() -> None:
    assert parse_chat_route_payload({"intent": "unknown", "answer": "x"}) is None


# ─── resolve_response_language ────────────────────────────────────────────


def test_resolve_response_language_defaults_to_primary() -> None:
    settings = _settings()
    body = CoachingRagRequest(question="Hello", response_language="")
    assert resolve_response_language(body, settings) == settings.deployment_primary_locale


def test_resolve_response_language_rejects_unsupported() -> None:
    settings = _settings()
    body = CoachingRagRequest(question="Hello", response_language="zz")
    with pytest.raises(CoachingRagError) as exc:
        resolve_response_language(body, settings)
    assert exc.value.status_code == 400
    assert "response_language must be one of" in str(exc.value)


def test_resolve_response_language_accepts_additional_locale() -> None:
    settings = _settings(deployment_additional_locales="en")
    body = CoachingRagRequest(question="Hello", response_language="en")
    assert resolve_response_language(body, settings) == "en"
    assert coaching_rag_response_locales(settings) == frozenset({"bn", "en"})


def test_resolve_response_language_rejects_en_without_additional_config() -> None:
    settings = _settings()
    body = CoachingRagRequest(question="Hello", response_language="en")
    with pytest.raises(CoachingRagError) as exc:
        resolve_response_language(body, settings)
    assert exc.value.status_code == 400


def test_settings_rejects_additional_duplicate_of_primary() -> None:
    with pytest.raises(ValidationError, match="must not include deployment_primary_locale"):
        Settings(deployment_primary_locale="bn", deployment_additional_locales="bn")


def test_settings_rejects_unknown_additional_locale() -> None:
    with pytest.raises(ValidationError, match="unknown locale"):
        Settings(deployment_primary_locale="bn", deployment_additional_locales="zz")


# ─── CoachingChatRouter.route ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_router_returns_none_on_ai_error() -> None:
    ai = AsyncMock()
    ai.generate = AsyncMock(return_value=_route_resp(error="boom"))
    router = CoachingChatRouter(MagicMock(spec=AsyncSession), ai)
    assert await router.route(question="Hello", lang="bn") is None


@pytest.mark.asyncio
async def test_router_parses_happy_path() -> None:
    ai = AsyncMock()
    ai.generate = AsyncMock(
        return_value=_route_resp(
            parsed_json={
                "intent": "chitchat",
                "confidence": "medium",
                "answer": "হাই!",
                "suggested_questions": [],
            }
        )
    )
    router = CoachingChatRouter(MagicMock(spec=AsyncSession), ai)
    result = await router.route(question="Hello", lang="bn")
    assert result is not None
    assert result.should_early_return is True
    assert result.answer == "হাই!"


@pytest.mark.asyncio
async def test_router_card_local_uses_local_card_template_and_generation_type() -> None:
    ai = AsyncMock()
    ai.generate = AsyncMock(
        return_value=_route_resp(
            parsed_json={
                "intent": "coaching_question",
                "confidence": "high",
                "answer": "",
            }
        )
    )
    router = CoachingChatRouter(MagicMock(spec=AsyncSession), ai)
    await router.route(question="What is ANC?", lang="bn", use_local=True, card_local=True)
    req = ai.generate.await_args.args[0]
    assert req.generation_type == GenerationType.COACHING_LOCAL_CARD_CHAT_ROUTE
    assert req.prompt.template_id == COACHING_LOCAL_CARD_CHAT_ROUTE_TEMPLATE_ID
    assert ai.generate.await_args.kwargs["use_local"] is True


# ─── CoachingRagService.query early branch ────────────────────────────────


@pytest.mark.asyncio
async def test_query_chitchat_early_return_skips_embed() -> None:
    ai = AsyncMock()
    ai.generate = AsyncMock(
        return_value=_route_resp(
            parsed_json={
                "intent": "chitchat",
                "confidence": "high",
                "answer": "Hello! Ask me a coaching question.",
                "suggested_questions": ["ANC steps?"],
            }
        )
    )
    ai.embed = AsyncMock()
    svc = _rag_svc(ai=ai)

    resp = await svc.query(CoachingRagRequest(question="Hello", response_language="bn"))

    assert resp.answer.startswith("Hello!")
    assert resp.retrieved_modules == []
    assert resp.source_documents == []
    assert resp.cited_module_ids == []
    assert resp.suggested_questions == ["ANC steps?"]
    assert resp.model == "gemini-route"
    ai.embed.assert_not_called()


@pytest.mark.asyncio
async def test_query_crisis_early_return_skips_embed() -> None:
    ai = AsyncMock()
    ai.generate = AsyncMock(
        return_value=_route_resp(
            parsed_json={
                "intent": "crisis",
                "confidence": "high",
                "answer": "Please contact local emergency services now.",
                "suggested_questions": [],
            }
        )
    )
    ai.embed = AsyncMock()
    svc = _rag_svc(ai=ai)

    resp = await svc.query(CoachingRagRequest(question="I want to kill myself", response_language="bn"))

    assert "emergency" in resp.answer.casefold()
    assert resp.retrieved_modules == []
    ai.embed.assert_not_called()


@pytest.mark.asyncio
async def test_query_router_unsure_falls_through_to_embed() -> None:
    ai = AsyncMock()
    ai.generate = AsyncMock(
        return_value=_route_resp(
            parsed_json={
                "intent": "coaching_question",
                "confidence": "high",
                "answer": "",
            }
        )
    )
    ai.embed = AsyncMock(side_effect=RuntimeError("stop-after-embed"))
    svc = _rag_svc(ai=ai)

    with pytest.raises(CoachingRagError, match="ai-runtime embed failed"):
        await svc.query(CoachingRagRequest(question="Hello", response_language="bn"))

    ai.embed.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_bad_locale_before_router_or_embed() -> None:
    ai = AsyncMock()
    svc = _rag_svc(ai=ai)

    with pytest.raises(CoachingRagError) as exc:
        await svc.query(CoachingRagRequest(question="Hello", response_language="xx"))
    assert exc.value.status_code == 400
    ai.generate.assert_not_called()
    ai.embed.assert_not_called()


@pytest.mark.asyncio
async def test_query_clinical_skips_router_calls_embed() -> None:
    ai = AsyncMock()
    ai.embed = AsyncMock(side_effect=RuntimeError("stop-after-embed"))
    svc = _rag_svc(ai=ai)

    with (
        patch(
            "platform_service.services.coaching_rag_service.should_route_chat",
            return_value=False,
        ),
        pytest.raises(CoachingRagError, match="ai-runtime embed failed"),
    ):
        await svc.query(
            CoachingRagRequest(
                question="What is the referral threshold for high BP?",
                response_language="bn",
            )
        )

    ai.generate.assert_not_called()
    ai.embed.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_use_local_passes_flag_to_embed_search_and_generate() -> None:
    mod_id = uuid4()
    mock_module = MagicMock()
    mock_module.id = mod_id
    mock_module.title_localized = {"bn": "Test"}
    mock_module.domain = "rmnch"

    ai = AsyncMock()
    ai.embed = AsyncMock(return_value=[[1.0] + [0.0] * 767])
    ai.generate = AsyncMock(
        return_value=InferenceResponse(
            request_id="r1",
            generation_type=GenerationType.COACHING_RAG,
            provider="local",
            model="qwen-local",
            max_tokens=1024,
            temperature=0.1,
            raw_text='{"answer": "Local answer", "cited_module_ids": [], "suggested_questions": []}',
            parsed_json={
                "answer": "Local answer",
                "cited_module_ids": [],
                "suggested_questions": [],
            },
            latency_ms=100,
            error=None,
        )
    )
    svc = _rag_svc(ai=ai)

    with (
        patch(
            "platform_service.services.coaching_rag_service.should_route_chat",
            return_value=False,
        ),
        patch("platform_service.services.coaching_rag_service.ModuleRepository") as repo_cls,
    ):
        repo = repo_cls.return_value
        repo.search_by_embedding = AsyncMock(return_value=[(mock_module, 0.1)])
        repo.list_cards_for_module_ids = AsyncMock(return_value=[])

        resp = await svc.query(
            CoachingRagRequest(
                question="What is ANC?",
                response_language="bn",
                use_local=True,
            )
        )

    ai.embed.assert_awaited_once_with(["What is ANC?"], use_local=True)
    repo.search_by_embedding.assert_awaited_once()
    assert repo.search_by_embedding.await_args.kwargs["use_local"] is True
    ai.generate.assert_awaited_once()
    assert ai.generate.await_args.kwargs["use_local"] is True
    req = ai.generate.await_args.args[0]
    assert req.generation_type == GenerationType.COACHING_RAG
    assert resp.answer == "Local answer"
    assert resp.model == "qwen-local"


# ─── CoachingRagService.local_query ─────────────────────────────────────


@pytest.mark.asyncio
async def test_local_query_chitchat_early_return_skips_embed() -> None:
    ai = AsyncMock()
    ai.generate = AsyncMock(
        return_value=_route_resp(
            parsed_json={
                "intent": "chitchat",
                "confidence": "high",
                "answer": "Hello! Ask me a coaching question.",
                "suggested_questions": ["ANC steps?"],
            }
        )
    )
    ai.embed = AsyncMock()
    svc = _rag_svc(ai=ai)

    resp = await svc.local_query(CoachingLocalRagRequest(question="Hello", response_language="bn"))

    assert resp.answer.startswith("Hello!")
    assert resp.retrieved_modules == []
    ai.embed.assert_not_called()
    ai.generate.assert_awaited_once()
    assert ai.generate.await_args.kwargs["use_local"] is True
    req = ai.generate.await_args.args[0]
    assert req.generation_type == GenerationType.COACHING_LOCAL_CARD_CHAT_ROUTE


@pytest.mark.asyncio
async def test_local_query_empty_card_corpus_returns_404() -> None:
    ai = AsyncMock()
    ai.embed = AsyncMock(return_value=[[1.0] + [0.0] * 767])
    svc = _rag_svc(ai=ai)

    with (
        patch(
            "platform_service.services.coaching_rag_service.should_route_chat",
            return_value=False,
        ),
        patch("platform_service.services.coaching_rag_service.ModuleRepository") as repo_cls,
    ):
        repo = repo_cls.return_value
        repo.search_cards_by_local_embedding = AsyncMock(return_value=[])

        with pytest.raises(CoachingRagError) as exc:
            await svc.local_query(CoachingLocalRagRequest(question="What is ANC?", response_language="bn"))

    assert exc.value.status_code == 404
    assert "backfill_module_card_local_embeddings" in str(exc.value)
    ai.embed.assert_awaited_once_with(["What is ANC?"], use_local=True)


@pytest.mark.asyncio
async def test_local_query_uses_card_search_and_local_generate() -> None:
    mod_id = uuid4()
    card_id = uuid4()
    mock_module = MagicMock()
    mock_module.id = mod_id
    mock_module.title_localized = {"bn": "Test"}
    mock_module.domain = "rmnch"

    mock_card = MagicMock()
    mock_card.id = card_id
    mock_card.module_id = mod_id
    mock_card.card_order = 0

    ai = AsyncMock()
    ai.embed = AsyncMock(return_value=[[1.0] + [0.0] * 767])
    ai.generate = AsyncMock(
        return_value=InferenceResponse(
            request_id="r1",
            generation_type=GenerationType.COACHING_LOCAL_CARD_RAG,
            provider="local",
            model="qwen-local",
            max_tokens=1024,
            temperature=0.1,
            raw_text='{"answer": "Local card answer", "cited_module_ids": [], "suggested_questions": []}',
            parsed_json={
                "answer": "Local card answer",
                "cited_module_ids": [],
                "suggested_questions": [],
            },
            latency_ms=100,
            error=None,
        )
    )
    svc = _rag_svc(ai=ai)

    with (
        patch(
            "platform_service.services.coaching_rag_service.should_route_chat",
            return_value=False,
        ),
        patch("platform_service.services.coaching_rag_service.ModuleRepository") as repo_cls,
        patch(
            "platform_service.services.coaching_rag_service.card_row_to_dict",
            return_value={"id": str(card_id), "title": {"bn": "Card"}, "body": {"bn": "Body"}},
        ),
    ):
        repo = repo_cls.return_value
        repo.search_cards_by_local_embedding = AsyncMock(return_value=[(mock_card, 0.1)])
        repo.list_modules_by_ids = AsyncMock(return_value=[mock_module])

        resp = await svc.local_query(CoachingLocalRagRequest(question="What is ANC?", response_language="bn"))

    ai.embed.assert_awaited_once_with(["What is ANC?"], use_local=True)
    repo.search_cards_by_local_embedding.assert_awaited_once()
    ai.generate.assert_awaited_once()
    assert ai.generate.await_args.kwargs["use_local"] is True
    req = ai.generate.await_args.args[0]
    assert req.generation_type == GenerationType.COACHING_LOCAL_CARD_RAG
    assert resp.answer == "Local card answer"
    assert len(resp.retrieved_modules) == 1
    assert resp.retrieved_modules[0].module_id == mod_id
    assert resp.retrieved_modules[0].cosine_distance == 0.1


@pytest.mark.asyncio
async def test_local_query_resolves_cited_card_ids_to_module_ids() -> None:
    mod_id = uuid4()
    card_id = uuid4()
    mock_module = MagicMock()
    mock_module.id = mod_id
    mock_module.title_localized = {"bn": "Test"}
    mock_module.domain = "rmnch"

    mock_card = MagicMock()
    mock_card.id = card_id
    mock_card.module_id = mod_id
    mock_card.card_order = 0

    ai = AsyncMock()
    ai.embed = AsyncMock(return_value=[[1.0] + [0.0] * 767])
    ai.generate = AsyncMock(
        return_value=InferenceResponse(
            request_id="r1",
            generation_type=GenerationType.COACHING_LOCAL_CARD_RAG,
            provider="local",
            model="qwen-local",
            max_tokens=1024,
            temperature=0.1,
            raw_text=(
                f'{{"answer": "Local card answer", '
                f'"cited_module_ids": ["{card_id}"], "suggested_questions": []}}'
            ),
            parsed_json={
                "answer": "Local card answer",
                "cited_module_ids": [str(card_id)],
                "suggested_questions": [],
            },
            latency_ms=100,
            error=None,
        )
    )
    svc = _rag_svc(ai=ai)

    with (
        patch(
            "platform_service.services.coaching_rag_service.should_route_chat",
            return_value=False,
        ),
        patch("platform_service.services.coaching_rag_service.ModuleRepository") as repo_cls,
        patch(
            "platform_service.services.coaching_rag_service.SourceRepository",
        ) as source_repo_cls,
        patch(
            "platform_service.services.coaching_rag_service.card_row_to_dict",
            return_value={"id": str(card_id), "title": {"bn": "Card"}, "body": {"bn": "Body"}},
        ),
    ):
        repo = repo_cls.return_value
        repo.search_cards_by_local_embedding = AsyncMock(return_value=[(mock_card, 0.1)])
        repo.list_modules_by_ids = AsyncMock(return_value=[mock_module])
        repo.list_cards_for_module_ids = AsyncMock(return_value=[])
        source_repo = source_repo_cls.return_value
        source_repo.list_block_provenance_by_ids = AsyncMock(return_value=[])
        source_repo.list_source_documents_by_ids = AsyncMock(return_value=[])

        resp = await svc.local_query(CoachingLocalRagRequest(question="What is ANC?", response_language="bn"))

    assert resp.cited_module_ids == [mod_id]
    attribution_calls = [invocation.args[0] for invocation in repo.list_modules_by_ids.await_args_list]
    assert [mod_id] in attribution_calls


def test_build_card_retrieval_context_emits_card_block() -> None:
    mod_id = uuid4()
    card_id = uuid4()
    mock_module = MagicMock()
    mock_module.id = mod_id

    mock_card = MagicMock()
    mock_card.id = card_id
    mock_card.module_id = mod_id

    ai = AsyncMock()
    svc = _rag_svc(ai=ai)

    with patch(
        "platform_service.services.coaching_rag_service.card_row_to_dict",
        return_value={"id": str(card_id), "title": {"bn": "Card title"}, "body": {"bn": "Card body"}},
    ):
        context = svc.build_card_retrieval_context(
            [(mock_card, 0.123456)],
            modules_by_id={mod_id: mock_module},
        )

    assert "CARD_BLOCK" in context
    assert f"card_id={card_id}" in context
    assert f"module_id={mod_id}" in context
    assert "cosine_distance=0.123456" in context
    assert "title[bn]: Card title" in context
    assert "body[bn]: Card body" in context
    assert "MODULE_BLOCK" not in context
