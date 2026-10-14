"""Base settings — extended by each service with service-specific fields."""

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    """Minimal settings shared by all services.

    Each service defines its own Settings subclass:
        class Settings(BaseAppSettings): ...
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "microcoaching"
    app_env: str = "development"
    log_level: str = "INFO"
    log_json: bool = True
    log_service_name: str | None = None
    # MICROCOACHING_LOG_DIR is the preferred name — LOG_DIR collides with the
    # same var in sibling Leapfrog services (e.g. leapfrog-ai-services) when
    # their envs are ever merged. log_dir kept as a fallback alias.
    log_dir: str | None = Field(
        default=None,
        validation_alias=AliasChoices("microcoaching_log_dir", "log_dir"),
    )
    log_max_bytes: int = 50_000_000
    log_backup_count: int = 10

    @field_validator("log_dir", mode="before")
    @classmethod
    def _empty_log_dir_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value
