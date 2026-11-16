"""Builders for object-storage tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from platform_service.objectstore.config import (
    GCS_DEFAULT_ENDPOINT,
    StorageConfig,
    StorageProvider,
)
from pydantic import SecretStr

_DEFAULT_ENDPOINTS = {
    StorageProvider.MINIO: "http://localhost:9000",
    StorageProvider.S3: None,
    StorageProvider.GCS: GCS_DEFAULT_ENDPOINT,
}
DEFAULT_PREFIXES = frozenset({"uploads", "ingest", "media", "source-documents"})


def storage_config(provider: str = "minio", **overrides: Any) -> StorageConfig:
    """A valid ``StorageConfig`` with a key pair; override any field."""
    kind = StorageProvider(provider)
    values: dict[str, Any] = {
        "provider": kind,
        "bucket": "test-bucket",
        "endpoint": _DEFAULT_ENDPOINTS[kind],
        "region": "us-east-1",
        "access_key": "k",
        "secret_key": "s",
        "public_endpoint": None,
        "create_bucket": False,
        "allowed_prefixes": DEFAULT_PREFIXES,
    }
    values.update(overrides)
    return StorageConfig(**values)


def storage_settings(**overrides: Any) -> SimpleNamespace:
    """The settings fields ``StorageConfig.from_settings`` reads, with nothing configured."""
    values: dict[str, Any] = {
        "app_env": "development",
        "storage_provider": None,
        "storage_bucket": "",
        "storage_endpoint": None,
        "storage_region": None,
        "storage_access_key": "",
        "storage_secret_key": "",
        "storage_public_endpoint": None,
        "storage_create_bucket": False,
        "admin_file_allowed_prefix_set": DEFAULT_PREFIXES,
    }
    values.update(overrides)
    for name in ("storage_access_key", "storage_secret_key"):
        values[name] = SecretStr(values[name])
    return SimpleNamespace(**values)
