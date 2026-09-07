"""AI runtime settings — extends mc_foundation BaseAppSettings."""

from __future__ import annotations

from functools import lru_cache
from typing import Self

from mc_contracts.internal_ai import AiProvider
from mc_foundation.config import BaseAppSettings
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import SettingsConfigDict

_DEV_INTERNAL_TOKEN = "dev-internal-token"
_DEPLOYED_ENVS = frozenset({"production", "staging"})


class Settings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ai-runtime"

    # ── Auth ─────────────────────────────────────────────────────────────────
    # Simple shared-secret token for internal service-to-service auth.
    # Platform sends X-Internal-Token header; we verify it here.
    internal_token: str = _DEV_INTERNAL_TOKEN

    # ── AI Provider ───────────────────────────────────────────────────────────
    # Single source of truth for generate / embed / transcribe routing.
    # Accepts ai_provider or legacy ai_cloud_provider env alias.
    ai_provider: AiProvider = Field(
        default="google",
        validation_alias=AliasChoices("ai_provider", "ai_cloud_provider"),
    )

    # Google Gemini — supports both Vertex AI and the Developer API.
    # google_use_vertex=true ⇒ ADC via GOOGLE_APPLICATION_CREDENTIALS env var
    # plus google_cloud_project / google_cloud_location.
    # Otherwise the SDK falls back to api-key auth via google_api_key.
    google_use_vertex: bool = True
    google_cloud_project: str | None = "microcoaching"
    google_cloud_location: str = "us-central1"
    google_api_key: str = "default=key"
    # Base64-encoded service-account JSON. When set, forces Vertex mode and
    # builds credentials in-process (no GOOGLE_APPLICATION_CREDENTIALS file
    # needed). Standard pattern for passing GCP credentials in container
    # deployments where mounting a JSON file isn't ergonomic.
    google_service_account_base64: str | None = None
    google_embedding_model: str = "gemini-embedding-001"
    google_embedding_dimension: int = 768

    # Local EmbeddingGemma (sentence-transformers) — used when embed request sets use_local.
    local_embedding_model: str = "google/embeddinggemma-300m"
    local_embedding_device: str = "cpu"
    huggingface_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("huggingface_token", "hf_token"),
    )
    local_embedding_cache_dir: str | None = None

    # Local generation — used when generate request sets use_local (GGUF via llama-cpp-python).
    local_generation_gguf_path: str | None = None
    local_generation_gguf_repo: str | None = "Qwen/Qwen3-0.6B-GGUF"
    local_generation_gguf_file: str | None = "Qwen3-0.6B-Instruct-Q4_K_M.gguf"
    local_generation_n_ctx: int = Field(default=32_768, ge=512, le=131_072)
    local_generation_n_threads: int | None = None
    local_generation_n_batch: int = Field(default=512, ge=8, le=4096)
    local_generation_max_input_tokens: int = Field(default=20_000, ge=256, le=131_072)
    local_preload_on_startup: bool = True

    google_transcription_model: str = "gemini-2.5-flash"

    # Target pgvector corpus dimension; the canonical truncation point lives in
    # ``services/embedding_vector.align_embedding_dimension`` and runs once per
    # ``PromptExecutor.embed`` call. Platform-side helpers assert against this
    # value instead of re-truncating.
    embedding_dimension: int = 768

    # ── Generation defaults ───────────────────────────────────────────────────
    # Used as fallback when a GenerationType is missing from GENERATION_PROFILES
    # (tests assert the map is complete). Per-type budgets live in
    # ``ai_runtime.generation_profiles``.
    default_inference_model: str = "gemini-2.5-flash"
    default_max_tokens: int = 8192
    default_temperature: float = 0.2
    json_parse_retries: int = 1
    json_parse_retries_local: int = 0
    # Log every successful LLM response body at INFO when true. Parse failures
    # are always logged at WARNING regardless of this flag.
    log_llm_responses: bool = True
    # Truncate logged LLM bodies beyond this length (full text still returned in
    # InferenceResponse.raw_text).
    log_llm_response_max_chars: int = 20000
    # Per-provider SDK HTTP timeout (seconds). Keep below platform httpx timeout
    # so ai-runtime fails fast instead of holding the upstream connection.
    provider_timeout_seconds: float = 590.0

    @property
    def local_generation_model_id(self) -> str:
        if self.local_generation_gguf_path:
            return self.local_generation_gguf_path
        if self.local_generation_gguf_repo and self.local_generation_gguf_file:
            return f"{self.local_generation_gguf_repo}/{self.local_generation_gguf_file}"
        return "llama_cpp"

    @model_validator(mode="after")
    def _validate_local_generation_context_budget(self) -> Self:
        if self.local_generation_max_input_tokens >= self.local_generation_n_ctx:
            raise ValueError(
                "LOCAL_GENERATION_MAX_INPUT_TOKENS must be less than "
                "LOCAL_GENERATION_N_CTX (output tokens need space in the context window)"
            )
        return self

    @model_validator(mode="after")
    def _validate_local_generation_gguf(self) -> Self:
        has_path = bool(self.local_generation_gguf_path)
        has_repo = bool(self.local_generation_gguf_repo and self.local_generation_gguf_file)
        if not has_path and not has_repo:
            raise ValueError(
                "Local generation requires LOCAL_GENERATION_GGUF_PATH or "
                "LOCAL_GENERATION_GGUF_REPO + LOCAL_GENERATION_GGUF_FILE"
            )
        return self

    @model_validator(mode="after")
    def _validate_production_safety(self) -> Self:
        if self.app_env not in _DEPLOYED_ENVS:
            return self
        errors: list[str] = []
        if self.internal_token == _DEV_INTERNAL_TOKEN:
            errors.append("INTERNAL_TOKEN must not use the dev default in production")
        if (
            self.ai_provider == "google"
            and not self.google_use_vertex
            and self.google_api_key
            in {
                "",
                "default=key",
            }
        ):
            errors.append("GOOGLE_API_KEY or Vertex credentials are required in production")
        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
