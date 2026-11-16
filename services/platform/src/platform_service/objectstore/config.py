"""Object-storage configuration: one provider switch and a provider-neutral set of settings.

``StorageConfig.from_settings`` is the single home of the per-provider rules. The stores depend on
this value object, not on the service ``Settings`` class.

Environment contract (see ``.env.example``):

    MICROCOACHING_STORAGE_PROVIDER         minio | s3 | gcs
    MICROCOACHING_STORAGE_BUCKET           bucket name
    MICROCOACHING_STORAGE_ENDPOINT         storage API URL (required for minio; optional for s3, gcs)
    MICROCOACHING_STORAGE_REGION           region (s3 / minio)
    MICROCOACHING_STORAGE_ACCESS_KEY       key pair; both empty = the identity attached to the
    MICROCOACHING_STORAGE_SECRET_KEY       workload (GCP service account / AWS role)
    MICROCOACHING_STORAGE_PUBLIC_ENDPOINT  host browsers use in download links, if not the endpoint
    MICROCOACHING_STORAGE_CREATE_BUCKET    create the bucket if missing (minio only)
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol
from urllib.parse import urlparse

from pydantic import SecretStr

from platform_service.config import DEPLOYED_ENVS
from platform_service.objectstore.naming import endpoint_url

ENV_PREFIX = "MICROCOACHING_STORAGE_"
GCS_DEFAULT_ENDPOINT = "https://storage.googleapis.com"
_GOOGLE_API_DOMAIN = "googleapis.com"
DEFAULT_REGION = "us-east-1"
# Keys shipped in docker-compose.yml / .env.example for the local MinIO; never valid when deployed.
LOCAL_DEV_KEYS = frozenset({"microcoaching", "microcoaching123", "minioadmin"})

# Pre-rename variable -> its replacement ("" = removed; the value is now derived).
LEGACY_ENV_RENAMES: dict[str, str] = {
    "OBJECT_STORAGE_BACKEND": f"{ENV_PREFIX}PROVIDER",
    "OBJECT_STORAGE_BUCKET_NAME": f"{ENV_PREFIX}BUCKET",
    "OBJECT_STORAGE_ENDPOINT": f"{ENV_PREFIX}ENDPOINT",
    "OBJECT_STORAGE_REGION": f"{ENV_PREFIX}REGION",
    "OBJECT_STORAGE_ACCESS_KEY": f"{ENV_PREFIX}ACCESS_KEY",
    "OBJECT_STORAGE_SECRET_KEY": f"{ENV_PREFIX}SECRET_KEY",
    "OBJECT_STORAGE_PRESIGNED_ENDPOINT": f"{ENV_PREFIX}PUBLIC_ENDPOINT",
    "OBJECT_STORAGE_AUTO_CREATE_BUCKET": f"{ENV_PREFIX}CREATE_BUCKET",
    "OBJECT_STORAGE_AUTH": "",
    "OBJECT_STORAGE_SECURE": "",
    "OBJECT_STORAGE_PRESIGN_MODE": "",
}


class StorageProvider(str, Enum):
    MINIO = "minio"
    S3 = "s3"
    GCS = "gcs"


class StorageConfigError(ValueError):
    """The object-storage settings are missing or contradict each other."""


class StorageSettings(Protocol):
    """The settings fields ``StorageConfig.from_settings`` reads."""

    app_env: str
    storage_provider: str | None
    storage_bucket: str
    storage_endpoint: str | None
    storage_region: str | None
    storage_access_key: SecretStr
    storage_secret_key: SecretStr
    storage_public_endpoint: str | None
    storage_create_bucket: bool

    @property
    def admin_file_allowed_prefix_set(self) -> frozenset[str]: ...


def legacy_env_names(environ: Mapping[str, str] | None = None) -> list[str]:
    """Pre-rename variables still present in the environment (matched case-insensitively).

    Only the process environment is inspected. A name that exists solely in a ``.env`` file read
    by ``Settings`` is not reported; it is not read either, so it has no effect.
    """
    present = {name.upper() for name in (os.environ if environ is None else environ)}
    return sorted(name for name in LEGACY_ENV_RENAMES if name in present)


def describe_legacy(names: list[str]) -> str:
    """One hint per leftover variable: what to rename it to, or that it can go."""
    hints = []
    for name in names:
        replacement = LEGACY_ENV_RENAMES[name]
        hints.append(f"{name} -> {replacement}" if replacement else f"{name} (remove; no longer used)")
    return "; ".join(hints)


@dataclass(frozen=True)
class StorageConfig:
    """Validated, provider-resolved object-storage settings."""

    provider: StorageProvider
    bucket: str
    endpoint: str | None
    region: str
    access_key: str = field(repr=False)
    secret_key: str = field(repr=False)
    public_endpoint: str | None
    create_bucket: bool
    allowed_prefixes: frozenset[str]

    @property
    def has_keys(self) -> bool:
        return bool(self.access_key and self.secret_key)

    @property
    def endpoint_is_google_https(self) -> bool:
        parsed = urlparse(self.endpoint or "")
        host = parsed.hostname or ""
        return parsed.scheme == "https" and (
            host == _GOOGLE_API_DOMAIN or host.endswith(f".{_GOOGLE_API_DOMAIN}")
        )

    @property
    def auth_description(self) -> str:
        """For the start-up log line; never includes a key."""
        return "access key" if self.has_keys else "attached workload identity"

    def describe(self) -> str:
        """One line for the start-up log; contains no credential."""
        return (
            f"provider={self.provider.value} bucket={self.bucket} "
            f"endpoint={self.endpoint or 'provider default'} auth={self.auth_description}"
        )

    @classmethod
    def from_settings(
        cls, settings: StorageSettings, *, environ: Mapping[str, str] | None = None
    ) -> StorageConfig:
        provider = _provider(settings.storage_provider, environ)
        bucket = (settings.storage_bucket or "").strip()
        if not bucket:
            raise StorageConfigError(f"{ENV_PREFIX}BUCKET is required")

        access = settings.storage_access_key.get_secret_value().strip()
        secret = settings.storage_secret_key.get_secret_value().strip()
        if bool(access) != bool(secret):
            raise StorageConfigError(
                f"{ENV_PREFIX}ACCESS_KEY and {ENV_PREFIX}SECRET_KEY must be set together "
                "(or both left empty to use the identity attached to the workload)"
            )

        config = cls(
            provider=provider,
            bucket=bucket,
            endpoint=_url(settings.storage_endpoint, "ENDPOINT") or _default_endpoint(provider),
            region=(settings.storage_region or "").strip() or DEFAULT_REGION,
            access_key=access,
            secret_key=secret,
            public_endpoint=_url(settings.storage_public_endpoint, "PUBLIC_ENDPOINT"),
            create_bucket=bool(settings.storage_create_bucket),
            allowed_prefixes=settings.admin_file_allowed_prefix_set,
        )
        config._check_provider_rules()
        config._check_deployed(settings.app_env)
        return config

    def _check_provider_rules(self) -> None:
        name = self.provider.value
        if self.provider is StorageProvider.MINIO:
            if not self.endpoint:
                raise StorageConfigError(f"{ENV_PREFIX}ENDPOINT is required when {ENV_PREFIX}PROVIDER=minio")
            if not self.has_keys:
                raise StorageConfigError(
                    f"{ENV_PREFIX}ACCESS_KEY and {ENV_PREFIX}SECRET_KEY are required "
                    f"when {ENV_PREFIX}PROVIDER=minio"
                )
            return
        if self.create_bucket:
            raise StorageConfigError(
                f"{ENV_PREFIX}CREATE_BUCKET is only allowed with {ENV_PREFIX}PROVIDER=minio; "
                f"create the {name} bucket in infrastructure"
            )
        if self.provider is StorageProvider.GCS and not self.has_keys and not self.endpoint_is_google_https:
            raise StorageConfigError(
                f"{ENV_PREFIX}ENDPOINT must be an https googleapis.com host when {ENV_PREFIX}PROVIDER=gcs runs "
                "without a key pair: the workload's bearer token is sent on every request"
            )
        if self.provider is StorageProvider.GCS and self.public_endpoint and not self.has_keys:
            raise StorageConfigError(
                f"{ENV_PREFIX}PUBLIC_ENDPOINT needs a key pair when {ENV_PREFIX}PROVIDER=gcs: links signed "
                "by the attached service account must point at Google Cloud Storage itself"
            )

    def _check_deployed(self, app_env: str) -> None:
        if app_env in DEPLOYED_ENVS and {self.access_key, self.secret_key} & LOCAL_DEV_KEYS:
            raise StorageConfigError(
                f"{ENV_PREFIX}ACCESS_KEY / {ENV_PREFIX}SECRET_KEY must not use the local development "
                f"values when app_env={app_env}"
            )


def _provider(raw: str | None, environ: Mapping[str, str] | None) -> StorageProvider:
    value = (raw or "").strip().lower()
    supported = ", ".join(p.value for p in StorageProvider)
    if not value:
        message = f"{ENV_PREFIX}PROVIDER is required (one of: {supported})"
        legacy = legacy_env_names(environ)
        if legacy:
            message += f". Found variables from before the rename: {describe_legacy(legacy)}"
        raise StorageConfigError(message)
    try:
        return StorageProvider(value)
    except ValueError:
        raise StorageConfigError(f"{ENV_PREFIX}PROVIDER must be one of: {supported}; got {raw!r}") from None


def _url(raw: str | None, suffix: str) -> str | None:
    try:
        return endpoint_url(raw)
    except ValueError as exc:
        raise StorageConfigError(f"{ENV_PREFIX}{suffix}: {exc}") from exc


def _default_endpoint(provider: StorageProvider) -> str | None:
    # s3 with no endpoint lets boto3 pick the regional AWS endpoint.
    return GCS_DEFAULT_ENDPOINT if provider is StorageProvider.GCS else None
