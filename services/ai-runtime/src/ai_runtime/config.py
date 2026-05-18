"""AI runtime settings — extends mc_foundation BaseAppSettings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from mc_foundation.config import BaseAppSettings
from pydantic_settings import SettingsConfigDict

AiProvider = Literal["google", "openai"]


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
    internal_token: str = "dev-internal-token"

    # ── AI Provider ───────────────────────────────────────────────────────────
    ai_provider: AiProvider = "google"

    # Google Gemini — supports both Vertex AI and the Developer API.
    # google_use_vertex=true ⇒ ADC via GOOGLE_APPLICATION_CREDENTIALS env var
    # plus google_cloud_project / google_cloud_location.
    # Otherwise the SDK falls back to api-key auth via google_api_key.
    google_use_vertex: bool = False
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    google_api_key: str = ""
    # Base64-encoded service-account JSON. When set, forces Vertex mode and
    # builds credentials in-process (no GOOGLE_APPLICATION_CREDENTIALS file
    # needed). Standard pattern for passing GCP credentials in container
    # deployments where mounting a JSON file isn't ergonomic.
    google_service_account_base64: str | None = None
    google_inference_model: str = "gemini-2.5-flash"
    google_embedding_model: str = "gemini-embedding-001"
    google_embedding_dimension: int = 768

    # OpenAI (future)
    openai_api_key: str = ""
    openai_inference_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # ── Generation defaults ───────────────────────────────────────────────────
    # 8192 gives Stage C (large corpus → multi-candidate JSON) and Stage D
    # (full card+quiz JSON with translations) headroom. Per-call overrides
    # via InferenceRequest.constraints.max_tokens still apply.
    default_max_tokens: int = 8192
    default_temperature: float = 0.2
    json_parse_retries: int = 1


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Refuse to start in production with the dev default token.
    if settings.app_env == "production" and settings.internal_token == "dev-internal-token":
        raise RuntimeError(
            "Refusing to start: AI_RUNTIME_TOKEN is still the dev default. "
            "Set a real token."
        )
    return settings
