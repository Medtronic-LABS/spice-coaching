"""Shared helpers for local text generation backends."""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class LocalGenerationBackend(Protocol):
    async def generate(
        self,
        *,
        system_prompt: str,
        human_message: str,
        max_tokens: int,
        temperature: float,
        output_format: str = "json",
    ) -> tuple[str, int, int]:
        """Return (raw_text, input_tokens, output_tokens)."""
        ...


def effective_max_input_tokens(
    *,
    n_ctx: int,
    max_input_tokens: int,
    max_tokens: int,
) -> int:
    """Cap prompt length so prompt + ``max_tokens`` fits in the context window."""
    reserved_for_output = max(max_tokens, 1)
    budget = max(n_ctx - reserved_for_output, 1)
    return min(max_input_tokens, budget)


def build_chat_messages(system_prompt: str, human_message: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": human_message})
    return messages


def strip_thinking_blocks(text: str) -> str:
    """Remove Qwen3 thinking blocks from decoded output."""
    open_tag = "<" + "think" + ">"
    close_tag = "</" + "think" + ">"
    start = text.find(open_tag)
    if start == -1:
        return text.strip()
    end = text.find(close_tag, start)
    if end == -1:
        return text.strip()
    return (text[:start] + text[end + len(close_tag) :]).strip()


def log_generation_token_counts(
    *,
    backend: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    logger.info(
        "Local generation complete backend=%s input_tokens=%d output_tokens=%d",
        backend,
        input_tokens,
        output_tokens,
    )
