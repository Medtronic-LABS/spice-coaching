"""LLM router for coaching chit-chat and crisis early exits."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from mc_contracts.enums import GenerationType
from mc_contracts.internal_ai import (
    GenerationConstraints,
    InferenceRequest,
    TraceContext,
)
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.services.llm_response_resolver import resolve_parsed_dict
from platform_service.services.prompt_registry import COACHING_CHAT_ROUTE_TEMPLATE_ID
from platform_service.services.prompt_template_service import PromptTemplateService, prompt_spec_from_rendered
from platform_service.services.prompt_variables.coaching_chat_route_variables import (
    build_coaching_chat_route_variables,
)

logger = logging.getLogger(__name__)

ChatIntent = Literal["chitchat", "crisis", "coaching_question"]
ChatConfidence = Literal["high", "medium", "low"]

_VALID_INTENTS: frozenset[str] = frozenset({"chitchat", "crisis", "coaching_question"})
_VALID_CONFIDENCE: frozenset[str] = frozenset({"high", "medium", "low"})
_EARLY_CHAT_CONFIDENCE: frozenset[str] = frozenset({"high", "medium"})


@dataclass(frozen=True, slots=True)
class CoachingChatRouteResult:
    intent: ChatIntent
    confidence: ChatConfidence
    answer: str
    suggested_questions: list[str] = field(default_factory=list)
    model: str = ""
    should_early_return: bool = False


def _parse_suggested_questions(raw: Any, *, max_count: int = 3) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max_count:
            break
    return out


def parse_chat_route_payload(
    payload: dict[str, Any],
    *,
    model: str = "",
) -> CoachingChatRouteResult | None:
    """Map router JSON to a result, or None when the caller should fall through to RAG."""
    intent_raw = payload.get("intent")
    if not isinstance(intent_raw, str) or intent_raw not in _VALID_INTENTS:
        return None
    intent: ChatIntent = intent_raw  # type: ignore[assignment]

    confidence_raw = payload.get("confidence")
    if not isinstance(confidence_raw, str) or confidence_raw not in _VALID_CONFIDENCE:
        confidence_raw = "low"
    confidence: ChatConfidence = confidence_raw  # type: ignore[assignment]

    answer_raw = payload.get("answer")
    answer = answer_raw.strip() if isinstance(answer_raw, str) else ""
    suggested = _parse_suggested_questions(payload.get("suggested_questions"))

    if intent == "crisis":
        if not answer:
            return None
        return CoachingChatRouteResult(
            intent=intent,
            confidence=confidence,
            answer=answer,
            suggested_questions=[],
            model=model,
            should_early_return=True,
        )

    if intent == "chitchat":
        if confidence not in _EARLY_CHAT_CONFIDENCE or not answer:
            return CoachingChatRouteResult(
                intent=intent,
                confidence=confidence,
                answer=answer,
                suggested_questions=suggested,
                model=model,
                should_early_return=False,
            )
        return CoachingChatRouteResult(
            intent=intent,
            confidence=confidence,
            answer=answer,
            suggested_questions=suggested,
            model=model,
            should_early_return=True,
        )

    return CoachingChatRouteResult(
        intent=intent,
        confidence=confidence,
        answer="",
        suggested_questions=[],
        model=model,
        should_early_return=False,
    )


class CoachingChatRouter:
    def __init__(
        self,
        session: AsyncSession,
        ai: AIRuntimeClient,
    ) -> None:
        self._session = session
        self._ai = ai

    async def route(self, *, question: str, lang: str) -> CoachingChatRouteResult | None:
        """Classify and optionally draft a reply. None means fall through to RAG."""
        rendered = await PromptTemplateService().render(
            self._session,
            template_id=COACHING_CHAT_ROUTE_TEMPLATE_ID,
            variant_key=None,
            variables=build_coaching_chat_route_variables(question=question, lang=lang),
        )
        request = InferenceRequest(
            request_id=str(uuid.uuid4()),
            generation_type=GenerationType.COACHING_CHAT_ROUTE,
            prompt=prompt_spec_from_rendered(rendered),
            constraints=GenerationConstraints(language=lang, output_format="json"),
            trace_context=TraceContext(),
            context={"question": question},
        )
        try:
            response = await self._ai.generate(request)
        except Exception:
            logger.exception("coaching chat route: ai-runtime generate failed")
            return None

        if response.error:
            logger.warning("coaching chat route: ai-runtime error: %s", response.error)
            return None

        try:
            payload = resolve_parsed_dict(response)
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("coaching chat route: bad LLM payload")
            return None

        return parse_chat_route_payload(payload, model=response.model or "")
