"""Tests for local EmbeddingGemma inference service."""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from ai_runtime.services import local_embedding
from ai_runtime.services.local_embedding import LocalEmbeddingService, get_local_embedding_service
from mc_foundation.problem import AppError


@pytest.fixture(autouse=True)
def _reset_local_embedding_state() -> None:
    local_embedding._model = None
    local_embedding._local_service = None
    yield
    local_embedding._model = None
    local_embedding._local_service = None


def _mock_model(*, dim: int = 768) -> MagicMock:
    model = MagicMock()
    model.encode.return_value = np.array([[0.1] * dim, [0.2] * dim])
    return model


class TestLocalEmbeddingService:
    @pytest.mark.asyncio
    async def test_embed_uses_document_prompt_in_thread(self) -> None:
        mock_model = _mock_model()
        mock_model.encode.return_value = np.array([[0.1] * 768, [0.2] * 768])
        with patch(
            "ai_runtime.services.local_embedding._get_model",
            new_callable=AsyncMock,
            return_value=mock_model,
        ):
            service = LocalEmbeddingService()
            vectors = await service.embed(["a", "b"])

        mock_model.encode.assert_called_once_with(
            ["a", "b"],
            normalize_embeddings=True,
            prompt_name="document",
        )
        assert len(vectors) == 2
        assert len(vectors[0]) == 768
        assert len(vectors[1]) == 768

    @pytest.mark.asyncio
    async def test_embed_single_text_returns_one_vector(self) -> None:
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.3] * 768)
        with patch(
            "ai_runtime.services.local_embedding._get_model",
            new_callable=AsyncMock,
            return_value=mock_model,
        ):
            vectors = await LocalEmbeddingService().embed(["only"])

        assert len(vectors) == 1
        assert len(vectors[0]) == 768

    @pytest.mark.asyncio
    async def test_inference_failure_raises_app_error(self) -> None:
        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("boom")
        with patch(
            "ai_runtime.services.local_embedding._get_model",
            new_callable=AsyncMock,
            return_value=mock_model,
        ):
            with pytest.raises(AppError) as exc_info:
                await LocalEmbeddingService().embed(["x"])
        assert exc_info.value.status == 502
        assert "local embedding inference failed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_lazy_loads_model_once(self) -> None:
        mock_model = _mock_model()
        with patch(
            "ai_runtime.services.local_embedding._load_model",
            return_value=mock_model,
        ) as load_model:
            service = get_local_embedding_service()
            await service.embed(["a"])
            await service.embed(["b"])

        load_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_model_load_failure_raises_app_error(self) -> None:
        with patch(
            "ai_runtime.services.local_embedding._load_model",
            side_effect=OSError("download failed"),
        ):
            with pytest.raises(AppError) as exc_info:
                await LocalEmbeddingService().embed(["x"])
        assert exc_info.value.status == 502
        assert "failed to load local embedding model" in exc_info.value.detail
