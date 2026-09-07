"""Eager-load local embedding and generation models at ai-runtime startup."""

from __future__ import annotations

import logging

from ai_runtime.config import get_settings
from ai_runtime.services.local_embedding import get_local_embedding_service
from ai_runtime.services.local_generation import get_local_generation_service

logger = logging.getLogger(__name__)


async def preload_local_models() -> None:
    settings = get_settings()
    if not settings.local_preload_on_startup:
        return

    logger.info("Preloading local embedding model")
    await get_local_embedding_service().embed(["warmup"])

    logger.info(
        "Preloading local generation model=%s",
        settings.local_generation_model_id,
    )
    await get_local_generation_service().generate(
        system_prompt='Reply with JSON: {"ok": true}',
        human_message="warmup",
        max_tokens=8,
        temperature=0.0,
        output_format="json",
    )
    logger.info("Local model preload complete")
