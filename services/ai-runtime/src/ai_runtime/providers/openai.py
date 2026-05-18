"""OpenAI provider adapter."""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from ai_runtime.providers.base import BaseProvider, ProviderImage

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """Adapter for OpenAI API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        organization: str | None = None,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            organization=organization,
        )

    async def generate(
        self,
        system_prompt: str,
        human_message: str,
        model: str,
        max_tokens: int,
        temperature: float,
        images: list[ProviderImage] | None = None,
        output_format: str = "text",
    ) -> tuple[str, int, int]:
        """Call OpenAI and return (raw_text, input_tokens, output_tokens)."""
        # OpenAI JSON mode requires the word 'json' in the prompt.
        if output_format == "json":
            if "json" not in system_prompt.lower() and "json" not in human_message.lower():
                system_prompt += "\n\nIMPORTANT: You must return the response in valid JSON format."

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        human_content: list[dict[str, Any]] = [{"type": "text", "text": human_message}]
        for img in images or []:
            import base64

            b64_data = base64.b64encode(img.data).decode("utf-8")
            human_content.append(
                {"type": "image_url", "image_url": {"url": f"data:{img.mime_type};base64,{b64_data}"}}
            )

        messages.append({"role": "user", "content": human_content})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if output_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        raw_text = choice.message.content or ""

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        return raw_text, input_tokens, output_tokens

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Return embedding vectors for the given texts."""
        response = await self._client.embeddings.create(
            model=model,
            input=texts,
        )
        # Sort by index to ensure order matches input
        data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in data]
