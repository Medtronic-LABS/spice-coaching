"""W-5 — Stage D card drafter via ai-runtime.

Per Pipeline v3.3 §7. Calls ai-runtime with GenerationType.CARD_DRAFTING and
parses the response into draft card dicts ready for snippet resolution and
persistence.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from mc_contracts.enums import GenerationType
from mc_contracts.internal_ai import (
    GenerationConstraints,
    InferenceRequest,
    ModelPolicy,
    PromptSpec,
    TraceContext,
)

from platform_service.config import get_settings
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.services.prompts.card_drafter_prompt import (
    CARD_DRAFTER_TEMPLATE_ID,
    CARD_DRAFTER_TEMPLATE_VERSION,
    render_human_message,
    render_system_prompt,
)

logger = logging.getLogger(__name__)


# Refusal reason vocabulary (per Pipeline v3.3 §7).
INSUFFICIENT_REASONS = (
    "no_actionable_content",
    "single_concept_only",
    "no_quiz_anchors",
    "language_imbalance_severe",
)


@dataclass(frozen=True)
class CardDrafterResult:
    """Outcome of one card-drafting call."""

    cards: list[dict[str, Any]]
    insufficient_reason: str | None  # set when LLM refused; cards is empty


class CardDrafterError(Exception):
    """Raised when ai-runtime errors out or output is structurally bad."""


class CardDrafter:
    """Single-call card drafter."""

    def __init__(
        self,
        client: AIRuntimeClient | None = None,
        *,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        self._client = client or AIRuntimeClient()
        self._model = model or settings.text_model

    async def draft(
        self,
        *,
        candidate: dict[str, Any],
        cited_blocks: list[dict[str, Any]],
        valid_block_ids: set[uuid.UUID],
        trace_context: TraceContext | None = None,
    ) -> CardDrafterResult:
        """Run the card drafter for one candidate.

        `cited_blocks` is the list of content_blocks the candidate's
        source_provenance pointed at (each a dict with content_block_id,
        block_type, content_text, content_language).
        """
        settings = get_settings()
        module_type = candidate.get("proposed_module_type", "refresher")

        system_prompt = render_system_prompt(
            module_type=module_type,
            card_min_count=settings.card_min_count,
            card_max_count=settings.card_max_count,
        )
        human_message = render_human_message(candidate=candidate, cited_blocks=cited_blocks)

        request = InferenceRequest(
            request_id=str(uuid.uuid4()),
            generation_type=GenerationType.CARD_DRAFTING,
            model_policy=ModelPolicy(provider=settings.ai_cloud_provider, model=self._model),
            prompt=PromptSpec(
                template_id=CARD_DRAFTER_TEMPLATE_ID,
                template_version=CARD_DRAFTER_TEMPLATE_VERSION,
                resolved_system_prompt=system_prompt,
                resolved_human_message=human_message,
            ),
            constraints=GenerationConstraints(language="bn", output_format="json"),
            trace_context=trace_context or TraceContext(),
        )
        response = await self._client.generate(request)
        if response.error:
            raise CardDrafterError(f"ai-runtime error: {response.error}")

        payload: Any = response.parsed_json
        if payload is None:
            try:
                payload = json.loads(response.raw_text)
            except json.JSONDecodeError as exc:
                raise CardDrafterError(f"LLM output is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise CardDrafterError(f"LLM output must be a JSON object, got {type(payload).__name__}")

        # Refusal path
        reason = payload.get("insufficient_for_drafting")
        if reason:
            if reason not in INSUFFICIENT_REASONS:
                logger.warning(
                    "Drafter returned unknown insufficient_for_drafting reason %r — allowing through",
                    reason,
                )
            return CardDrafterResult(cards=[], insufficient_reason=str(reason))

        cards_raw = payload.get("cards")
        if not isinstance(cards_raw, list):
            raise CardDrafterError("LLM output missing 'cards' list")

        # Normalize + validate each card.
        cards: list[dict[str, Any]] = []
        for raw_card in cards_raw:
            if not isinstance(raw_card, dict):
                continue
            normalised = _normalise_card(
                raw_card,
                module_type=module_type,
                valid_block_ids=valid_block_ids,
            )
            if normalised is not None:
                cards.append(normalised)

        # Cap at max — preserves the count guidance for the LLM but lets
        # us truncate long outputs gracefully.
        if len(cards) > settings.card_max_count:
            logger.info("Card drafter returned %d cards; capping to %d", len(cards), settings.card_max_count)
            cards = cards[: settings.card_max_count]

        # Per the architecture reset, the drafter no longer rejects on
        # min-count: a 1-card module is still a renderable module, and
        # rejection wastes the candidate. The dashboard surfaces low-card
        # modules via `quality_flags` for clinician review instead.
        # If `cards == []` after validation, that's the "no salvageable
        # output" path — keep the explicit signal.
        if not cards:
            return CardDrafterResult(cards=[], insufficient_reason="no_actionable_content")

        # Always stamp a fresh server-issued UUID for `card_family_id`.
        # We never trust an LLM-supplied value (it's free-form and the
        # validator only requires a `str`) — runtime joins on this field
        # so a hallucinated non-UUID would corrupt module_quiz_question's
        # primary_card_family_id pointer.
        for c in cards:
            c["card_family_id"] = str(uuid.uuid4())

        return CardDrafterResult(cards=cards, insufficient_reason=None)


def _normalise_card(
    raw: dict[str, Any],
    *,
    module_type: str,
    valid_block_ids: set[uuid.UUID],
) -> dict[str, Any] | None:
    """Per-card validation. Returns the cleaned card dict, or None if invalid."""
    # Common required fields. `initial_training` shares the body_bn rule
    # with refresher/digital_proficiency — comprehensive training cards
    # without body content are unrenderable; the original elif-chain
    # silently let them through.
    if module_type in ("refresher", "digital_proficiency", "initial_training"):
        if not (raw.get("body_bn") or "").strip():
            logger.warning(
                "Rejecting card: %s requires body_bn",
                module_type,
            )
            return None
    elif module_type == "content_update":
        for f in ("previous_practice_bn", "current_practice_bn", "rationale_for_change_bn"):
            if not (raw.get(f) or "").strip():
                logger.warning("Rejecting content_update card: missing required field %r", f)
                return None
    if not (raw.get("title_bn") or "").strip():
        logger.warning("Rejecting card: missing title_bn")
        return None

    # Validate source_block_ids
    block_ids_raw = raw.get("source_block_ids", []) or []
    valid_blocks: list[str] = []
    for bid_raw in block_ids_raw:
        try:
            bid = uuid.UUID(str(bid_raw))
        except (TypeError, ValueError):
            continue
        if bid in valid_block_ids:
            valid_blocks.append(str(bid))
    if not valid_blocks:
        logger.warning("Rejecting card: no valid source_block_ids")
        return None
    raw["source_block_ids"] = valid_blocks

    # figure_ref must reference a valid block id (if present)
    fig_raw = raw.get("figure_ref_block_id")
    if fig_raw:
        try:
            fig_uuid = uuid.UUID(str(fig_raw))
        except (TypeError, ValueError):
            raw["figure_ref_block_id"] = None
        else:
            if fig_uuid not in valid_block_ids:
                raw["figure_ref_block_id"] = None
            else:
                raw["figure_ref_block_id"] = str(fig_uuid)

    return raw
