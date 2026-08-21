"""Unit tests for coaching chat router parse + RAG early-exit wiring."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mc_contracts.coaching import CoachingRagRequest
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
