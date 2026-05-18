"""Prompt executor — selects provider and runs inference.

ai-runtime owns the provider selection logic. Platform passes ModelPolicy
(provider + model); executor honours it or falls back to configured defaults.

v3.3 additions:
- Decodes optional `image_attachments` (base64) from InferenceRequest into
  `ProviderImage` (raw bytes) and forwards to the provider for multimodal
  calls (VISION_EXTRACTION).
- New generation types (outline_inference, module_identification,
  card_drafting, quiz_drafting, distractor_critique, bilingual_translation,
  vision_extraction) are dispatched the same way as the legacy types — the
  caller (platform) is responsible for the resolved prompt and structured
  output expectations; the executor is generation_type-agnostic at the
  provider call level.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import time

from mc_contracts.internal_ai import InferenceImage, InferenceRequest, InferenceResponse, TokenUsage

from ai_runtime.config import get_settings
from ai_runtime.providers.base import BaseProvider, ProviderImage
from ai_runtime.providers.google import GoogleProvider
from ai_runtime.providers.openai import OpenAIProvider
from ai_runtime.services.response_parser import extract_json

logger = logging.getLogger(__name__)


# Tokens that mark an exception as PERMANENT — retrying won't help.
# Anything else is treated as transient (timeouts, 5xx, connection drops, and
# 429 RESOURCE_EXHAUSTED quota responses).
#
# RESOURCE_EXHAUSTED was previously listed as permanent on the reasoning that
# "retrying inside the same minute won't help" — true, but the right answer is
# to wait long enough to span the quota window, not to give up. Per-minute
# quotas refill at the start of the next minute, so a 60-90s total backoff
# budget reliably clears them. The Stage 1 vision_failed cluster on the SK
# manual was 24% of pages because every 429 was being treated as permanent.
_PERMANENT_ERROR_MARKERS = (
    "INVALID_ARGUMENT",
    "PERMISSION_DENIED",
    "UNAUTHENTICATED",
    "NOT_FOUND",
    "FAILED_PRECONDITION",
    " 400 ",
    " 401 ",
    " 403 ",
    " 404 ",
    "code': 400",
    "code': 401",
    "code': 403",
    "code': 404",
)
# Backoffs span past the typical 60s per-minute quota refill window. With
# the previous (2.0, 5.0, 10.0) totalling 17s, retries were guaranteed to
# hit the same exhausted bucket. (10.0, 30.0, 60.0) → 100s total, with
# the longest delay alone covering the worst-case quota window.
_RETRY_BACKOFFS_S = (10.0, 30.0, 60.0)


def _is_transient(exc: Exception) -> bool:
    """Heuristic: treat connection / timeout / 5xx errors as transient. We err
    on the side of retrying — if we mis-classify a permanent error as
    transient we just waste a few seconds before returning it."""
    msg = str(exc) or type(exc).__name__
    return not any(m in msg for m in _PERMANENT_ERROR_MARKERS)


def _get_provider(provider_name: str) -> BaseProvider:
    settings = get_settings()
    if provider_name == "google":
        service_account_info = None
        if settings.google_service_account_base64:
            try:
                decoded = base64.b64decode(settings.google_service_account_base64).decode("utf-8")
                service_account_info = json.loads(decoded)
            except Exception as exc:
                logger.error("Failed to decode google_service_account_base64: %s", exc)
                # Fall through to other auth paths; GoogleProvider will raise
                # a clear error if no usable credentials remain.
        if service_account_info or settings.google_use_vertex:
            return GoogleProvider(
                use_vertex=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
                service_account_info=service_account_info,
                embedding_dimension=settings.google_embedding_dimension,
            )
        return GoogleProvider(
            api_key=settings.google_api_key,
            embedding_dimension=settings.google_embedding_dimension,
        )
    elif provider_name == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
        )
    raise ValueError(f"Unsupported provider: {provider_name}")


def _decode_image_attachments(attachments: list[InferenceImage]) -> list[ProviderImage]:
    """Decode base64 image attachments to raw bytes for the provider call.

    Raises ValueError on malformed base64 (caller catches and returns an
    InferenceResponse with `error` populated).
    """
    decoded: list[ProviderImage] = []
    for idx, att in enumerate(attachments):
        try:
            data = base64.b64decode(att.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                f"image_attachments[{idx}] (label={att.label!r}) is not valid base64: {exc}"
            ) from exc
        decoded.append(ProviderImage(data=data, mime_type=att.mime_type, label=att.label))
    return decoded


class PromptExecutor:
    """Executes an InferenceRequest against the appropriate AI provider."""

    def __init__(self) -> None:
        self._settings = get_settings()

    async def execute(self, request: InferenceRequest) -> InferenceResponse:
        settings = self._settings
        provider_name = request.model_policy.provider
        model = request.model_policy.model

        max_tokens = (
            request.constraints.max_tokens
            if request.constraints.max_tokens is not None
            else settings.default_max_tokens
        )
        temperature = (
            request.constraints.temperature
            if request.constraints.temperature is not None
            else settings.default_temperature
        )

        # Decode image attachments before timing the provider call so that
        # base64 errors are surfaced as a clean InferenceResponse.
        try:
            provider_images = _decode_image_attachments(request.image_attachments)
        except ValueError as exc:
            logger.error(
                "Image attachment decode failed request_id=%s: %s",
                request.request_id,
                exc,
            )
            return InferenceResponse(
                request_id=request.request_id,
                generation_type=request.generation_type,
                provider=provider_name,
                model=model,
                raw_text="",
                parsed_json=None,
                latency_ms=0,
                error=str(exc),
            )

        provider = _get_provider(provider_name)
        start_ms = time.monotonic()

        # Retry transient transport errors (Vertex auth-layer timeouts,
        # 5xx, connection drops). Permanent errors (4xx, INVALID_ARGUMENT)
        # short-circuit immediately so the caller sees the real reason.
        last_exc: Exception | None = None
        raw_text = ""
        input_tokens = 0
        output_tokens = 0
        for attempt in range(len(_RETRY_BACKOFFS_S) + 1):
            try:
                raw_text, input_tokens, output_tokens = await provider.generate(
                    system_prompt=request.prompt.resolved_system_prompt,
                    human_message=request.prompt.resolved_human_message,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    images=provider_images or None,
                )
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                transient = _is_transient(exc)
                final = attempt >= len(_RETRY_BACKOFFS_S)
                if not transient or final:
                    logger.exception(
                        "Provider error request_id=%s provider=%s model=%s attempt=%d transient=%s",
                        request.request_id,
                        provider_name,
                        model,
                        attempt + 1,
                        transient,
                    )
                    break
                wait = _RETRY_BACKOFFS_S[attempt]
                logger.warning(
                    "Transient provider error request_id=%s attempt=%d/%d retrying in %.1fs: %s",
                    request.request_id,
                    attempt + 1,
                    len(_RETRY_BACKOFFS_S) + 1,
                    wait,
                    exc,
                )
                await asyncio.sleep(wait)

        if last_exc is not None:
            latency_ms = int((time.monotonic() - start_ms) * 1000)
            return InferenceResponse(
                request_id=request.request_id,
                generation_type=request.generation_type,
                provider=provider_name,
                model=model,
                raw_text="",
                parsed_json=None,
                latency_ms=latency_ms,
                error=str(last_exc),
            )
        latency_ms = int((time.monotonic() - start_ms) * 1000)
        error = None

        parsed_json = None
        if request.constraints.output_format == "json":
            parsed_json = extract_json(raw_text)
            if parsed_json is None and not error:
                # Retry once on JSON parse failure
                if settings.json_parse_retries > 0:
                    logger.info("JSON parse failed, retrying request_id=%s", request.request_id)
                    try:
                        raw_text2, it2, ot2 = await provider.generate(
                            system_prompt=request.prompt.resolved_system_prompt,
                            human_message=request.prompt.resolved_human_message,
                            model=model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            images=provider_images or None,
                        )
                        parsed_json = extract_json(raw_text2)
                        if parsed_json is not None:
                            raw_text = raw_text2
                            input_tokens += it2
                            output_tokens += ot2
                    except Exception:
                        logger.warning("Retry also failed request_id=%s", request.request_id)

        # parsed_json may be a dict OR a list (top-level JSON arrays are valid
        # for module_identification, distractor_critique, etc.). Both are
        # surfaced via the same field; downstream typing on the response
        # accepts either by widening the field annotation in mc_contracts.
        return InferenceResponse(
            request_id=request.request_id,
            generation_type=request.generation_type,
            provider=provider_name,
            model=model,
            raw_text=raw_text,
            parsed_json=parsed_json,
            latency_ms=latency_ms,
            token_usage=TokenUsage(input=input_tokens, output=output_tokens),
            error=error,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings using the configured provider."""
        settings = self._settings
        provider = _get_provider(settings.ai_provider)

        if settings.ai_provider == "google":
            model = settings.google_embedding_model
        else:
            model = settings.openai_embedding_model

        return await provider.embed(texts, model=model)
