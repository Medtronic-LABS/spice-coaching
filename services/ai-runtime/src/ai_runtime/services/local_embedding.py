"""Local embedding inference via EmbeddingGemma (sentence-transformers)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError

from ai_runtime.config import get_settings

if TYPE_CHECKING:
    # Native lib: annotation only — runtime import stays inside _load_model.
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None
_model_lock = asyncio.Lock()


def _load_model() -> SentenceTransformer:
    """Load SentenceTransformer synchronously (called from a worker thread)."""
    # Native lib: importing sentence_transformers at module top would load torch
    # on every ai-runtime start via prompt_executor → local_embedding.
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    model_kwargs: dict[str, str] = {}
    if settings.huggingface_token:
        model_kwargs["token"] = settings.huggingface_token

    model = SentenceTransformer(
        settings.local_embedding_model,
        cache_folder=settings.local_embedding_cache_dir,
        **model_kwargs,
    )
    return model.to(settings.local_embedding_device)


async def _get_model() -> SentenceTransformer:
    global _model
    if _model is not None:
        return _model
    async with _model_lock:
        if _model is not None:
            return _model
        try:
            _model = await asyncio.to_thread(_load_model)
            logger.info(
                "Loaded local embedding model model=%s device=%s",
                get_settings().local_embedding_model,
                get_settings().local_embedding_device,
            )
        except Exception as exc:
            logger.exception("Failed to load local embedding model")
            raise AppError(
                ErrorCode.EMBEDDING_FAILED.value,
                f"failed to load local embedding model: {exc}",
                status=502,
            ) from exc
    return _model


def _encode_documents(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        prompt_name="document",
    )
    as_list = vectors.tolist()
    if as_list and isinstance(as_list[0], float):
        return [as_list]
    return as_list


class LocalEmbeddingService:
    """Lazy-loaded EmbeddingGemma encoder for offline/device-parity embeddings."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        model = await _get_model()
        try:
            return await asyncio.to_thread(_encode_documents, model, texts)
        except AppError:
            raise
        except Exception as exc:
            logger.exception("Local embedding inference failed")
            raise AppError(
                ErrorCode.EMBEDDING_FAILED.value,
                f"local embedding inference failed: {exc}",
                status=502,
            ) from exc


_local_service: LocalEmbeddingService | None = None


def get_local_embedding_service() -> LocalEmbeddingService:
    global _local_service
    if _local_service is None:
        _local_service = LocalEmbeddingService()
    return _local_service
