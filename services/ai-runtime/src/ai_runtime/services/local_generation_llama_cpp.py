"""Local text generation via llama.cpp (GGUF)."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from typing import Any

from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError

from ai_runtime.config import get_settings
from ai_runtime.services.local_generation_base import (
    build_chat_messages,
    effective_max_input_tokens,
    log_generation_token_counts,
    strip_thinking_blocks,
)

logger = logging.getLogger(__name__)

_llama: Any | None = None
_model_lock = asyncio.Lock()


def _llama_load_kwargs() -> dict[str, Any]:
    settings = get_settings()
    n_threads = settings.local_generation_n_threads
    if n_threads is None:
        n_threads = os.cpu_count() or 4
    return {
        "n_ctx": settings.local_generation_n_ctx,
        "n_threads": n_threads,
        "n_batch": settings.local_generation_n_batch,
        "verbose": False,
    }


def _load_llama() -> Any:
    try:
        # Native lib: importing llama_cpp at module top would load it on every
        # ai-runtime start via prompt_executor → local_generation.
        from llama_cpp import Llama
    except ImportError as exc:
        raise AppError(
            ErrorCode.GENERATION_FAILED.value,
            "llama-cpp-python is not installed; install ai-runtime with llama-cpp-python",
            status=502,
        ) from exc

    settings = get_settings()
    llama_kwargs = _llama_load_kwargs()
    hf_kwargs: dict[str, Any] = {}
    if settings.huggingface_token:
        hf_kwargs["token"] = settings.huggingface_token

    if settings.local_generation_gguf_path:
        return Llama(model_path=settings.local_generation_gguf_path, **llama_kwargs)

    if settings.local_generation_gguf_repo and settings.local_generation_gguf_file:
        return Llama.from_pretrained(
            repo_id=settings.local_generation_gguf_repo,
            filename=settings.local_generation_gguf_file,
            **llama_kwargs,
            **hf_kwargs,
        )

    raise AppError(
        ErrorCode.GENERATION_FAILED.value,
        "llama_cpp backend requires LOCAL_GENERATION_GGUF_PATH or "
        "LOCAL_GENERATION_GGUF_REPO + LOCAL_GENERATION_GGUF_FILE",
        status=502,
    )


async def _get_llama() -> Any:
    global _llama
    if _llama is not None:
        return _llama
    async with _model_lock:
        if _llama is not None:
            return _llama
        try:
            _llama = await asyncio.to_thread(_load_llama)
            settings = get_settings()
            model_id = settings.local_generation_model_id
            logger.info(
                "Loaded local generation model backend=llama_cpp model=%s n_ctx=%d",
                model_id,
                settings.local_generation_n_ctx,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.exception("Failed to load local llama.cpp model")
            raise AppError(
                ErrorCode.GENERATION_FAILED.value,
                f"failed to load local llama.cpp model: {exc}",
                status=502,
            ) from exc
    return _llama


def _resolve_chat_formatter(llama: Any) -> Callable[..., Any]:
    # Native lib: same deferred llama_cpp load as _load_llama.
    from llama_cpp import llama_chat_format

    handler = (
        llama.chat_handler
        or llama._chat_handlers.get(llama.chat_format)
        or llama_chat_format.get_chat_completion_handler(llama.chat_format)
    )
    closure = getattr(handler, "__closure__", None)
    if closure:
        formatter = closure[0].cell_contents
        if callable(formatter):
            return formatter
    if callable(handler):
        return handler
    raise AppError(
        ErrorCode.GENERATION_FAILED.value,
        "failed to resolve llama.cpp chat formatter for local generation",
        status=502,
    )


def _messages_to_prompt_tokens(
    llama: Any,
    messages: list[dict[str, str]],
) -> tuple[Any, list[int]]:
    formatter_result = _resolve_chat_formatter(llama)(messages=messages)
    prompt_tokens = llama.tokenize(
        formatter_result.prompt.encode("utf-8"),
        add_bos=not formatter_result.added_special,
        special=True,
    )
    return formatter_result, prompt_tokens


def _truncate_prompt_tokens(
    prompt_tokens: list[int],
    *,
    max_input_tokens: int,
) -> list[int]:
    if max_input_tokens <= 0 or len(prompt_tokens) <= max_input_tokens:
        return prompt_tokens
    logger.info(
        "Truncating local generation input from %d to %d tokens (keeping tail)",
        len(prompt_tokens),
        max_input_tokens,
    )
    return prompt_tokens[-max_input_tokens:]


def _json_grammar(llama: Any) -> Any:
    # Native lib: same deferred llama_cpp load as _load_llama.
    from llama_cpp.llama_grammar import JSON_GBNF, LlamaGrammar

    return LlamaGrammar.from_string(JSON_GBNF, verbose=llama.verbose)


def _completion_stop_tokens(formatter_result: Any) -> list[str]:
    if formatter_result.stop is None:
        return []
    if isinstance(formatter_result.stop, list):
        return list(formatter_result.stop)
    return [formatter_result.stop]


def _parse_chat_completion_response(response: Any) -> tuple[str, int, int]:
    choice = response["choices"][0]
    message = choice.get("message") or {}
    raw_text = strip_thinking_blocks(str(message.get("content") or ""))

    usage = response.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    if input_tokens == 0 and output_tokens == 0:
        output_tokens = max(len(raw_text.split()), 1)

    return raw_text, input_tokens, output_tokens


def _parse_completion_response(response: Any) -> tuple[str, int, int]:
    choice = response["choices"][0]
    raw_text = strip_thinking_blocks(str(choice.get("text") or ""))

    usage = response.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    if input_tokens == 0 and output_tokens == 0:
        output_tokens = max(len(raw_text.split()), 1)

    return raw_text, input_tokens, output_tokens


def _generate_sync(
    llama: Any,
    *,
    system_prompt: str,
    human_message: str,
    max_tokens: int,
    temperature: float,
    output_format: str,
    max_input_tokens: int,
) -> tuple[str, int, int]:
    messages = build_chat_messages(system_prompt, human_message)
    completion_kwargs: dict[str, Any] = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": max(temperature, 0.0),
    }
    if output_format == "json":
        completion_kwargs["response_format"] = {"type": "json_object"}

    if max_input_tokens > 0:
        n_ctx = llama.n_ctx()
        input_budget = effective_max_input_tokens(
            n_ctx=n_ctx,
            max_input_tokens=max_input_tokens,
            max_tokens=max_tokens,
        )
        formatter_result, prompt_tokens = _messages_to_prompt_tokens(llama, messages)
        truncated_prompt_tokens = _truncate_prompt_tokens(
            prompt_tokens,
            max_input_tokens=input_budget,
        )
        if truncated_prompt_tokens is not prompt_tokens:
            completion = llama.create_completion(
                prompt=truncated_prompt_tokens,
                max_tokens=max_tokens,
                temperature=max(temperature, 0.0),
                stop=_completion_stop_tokens(formatter_result),
                grammar=_json_grammar(llama) if output_format == "json" else None,
            )
            return _parse_completion_response(completion)

    response = llama.create_chat_completion(**completion_kwargs)
    return _parse_chat_completion_response(response)


class LlamaCppLocalGenerationService:
    """Lazy-loaded llama.cpp backend for fast CPU local generation."""

    async def generate(
        self,
        *,
        system_prompt: str,
        human_message: str,
        max_tokens: int,
        temperature: float,
        output_format: str = "json",
    ) -> tuple[str, int, int]:
        llama = await _get_llama()
        settings = get_settings()
        try:
            raw_text, input_tokens, output_tokens = await asyncio.to_thread(
                _generate_sync,
                llama,
                system_prompt=system_prompt,
                human_message=human_message,
                max_tokens=max_tokens,
                temperature=temperature,
                output_format=output_format,
                max_input_tokens=settings.local_generation_max_input_tokens,
            )
            log_generation_token_counts(
                backend="llama_cpp",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            return raw_text, input_tokens, output_tokens
        except AppError:
            raise
        except Exception as exc:
            logger.exception("Local llama.cpp generation inference failed")
            raise AppError(
                ErrorCode.GENERATION_FAILED.value,
                f"local llama.cpp generation inference failed: {exc}",
                status=502,
            ) from exc
