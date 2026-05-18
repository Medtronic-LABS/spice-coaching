"""HTTP client for the internal ai-runtime service.

Platform assembles fully-resolved InferenceRequest objects and posts them to
ai-runtime. AI runtime owns all LLM provider adapters; platform owns all state.
"""

from __future__ import annotations

import logging

import httpx
from mc_contracts.internal_ai import InferenceRequest, InferenceResponse

from platform_service.config import get_settings

logger = logging.getLogger(__name__)


class AIRuntimeClient:
    """Thin httpx client for ai-runtime internal API.

    Intended to be constructed per-request (or shared as a singleton with a
    managed httpx.AsyncClient lifecycle — see deps.py).
    """

    def __init__(
        self, base_url: str | None = None, token: str | None = None, timeout: float | None = None
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ai_runtime_base_url).rstrip("/")
        self._token = token or settings.ai_runtime_token
        self._timeout = timeout or settings.ai_runtime_timeout_seconds

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """Post a fully-resolved InferenceRequest to ai-runtime and return the response."""
        url = f"{self._base_url}/internal/generate/{request.generation_type.value}"
        headers = {"X-Internal-Token": self._token, "Content-Type": "application/json"}
        payload = request.model_dump(mode="json")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return InferenceResponse.model_validate(resp.json())
        except httpx.HTTPStatusError as exc:
            logger.error(
                "ai-runtime returned %s for generation_type=%s request_id=%s: %s",
                exc.response.status_code,
                request.generation_type.value,
                request.request_id,
                exc.response.text[:200],
            )
            raise
        except httpx.RequestError as exc:
            logger.error(
                "ai-runtime unreachable generation_type=%s request_id=%s: %s",
                request.generation_type.value,
                request.request_id,
                exc,
            )
            raise

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Request text embeddings from ai-runtime.

        Returns a list of embedding vectors (one per input text), in the same order.
        """
        url = f"{self._base_url}/internal/embed"
        headers = {"X-Internal-Token": self._token, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json={"texts": texts}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"]
