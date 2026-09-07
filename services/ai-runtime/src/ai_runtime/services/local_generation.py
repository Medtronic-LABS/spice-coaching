"""Local text generation via llama.cpp (GGUF)."""

from __future__ import annotations

from ai_runtime.services.local_generation_llama_cpp import LlamaCppLocalGenerationService

LocalGenerationService = LlamaCppLocalGenerationService

_local_service: LlamaCppLocalGenerationService | None = None


def get_local_generation_service() -> LlamaCppLocalGenerationService:
    global _local_service
    if _local_service is None:
        _local_service = LlamaCppLocalGenerationService()
    return _local_service


def reset_local_generation_services_for_tests() -> None:
    """Clear cached backend singleton (tests only)."""
    global _local_service
    _local_service = None
