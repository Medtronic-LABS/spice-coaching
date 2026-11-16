"""Build the configured ``ObjectStore`` for API / worker processes."""

from __future__ import annotations

import logging
from collections.abc import Callable

from mc_foundation.objectstore import ObjectStore

from platform_service.config import Settings, get_settings
from platform_service.objectstore.boto_store import BotoObjectStore
from platform_service.objectstore.config import (
    StorageConfig,
    StorageProvider,
    describe_legacy,
    legacy_env_names,
)
from platform_service.objectstore.gcs_store import GcsObjectStore
from platform_service.objectstore.minio_store import MinioObjectStore
from platform_service.objectstore.s3_store import S3ObjectStore

logger = logging.getLogger(__name__)

# Each provider store is built from the config alone.
_STORES: dict[StorageProvider, Callable[[StorageConfig], BotoObjectStore]] = {
    StorageProvider.MINIO: MinioObjectStore,
    StorageProvider.S3: S3ObjectStore,
    StorageProvider.GCS: GcsObjectStore,
}


def create_object_store(*, settings: Settings | None = None) -> BotoObjectStore:
    """Return the store selected by ``MICROCOACHING_STORAGE_PROVIDER``.

    Raises ``StorageConfigError`` (a ``ValueError``) naming the setting when the configuration is
    missing or inconsistent. Silent: services build a store per instance, so the start-up paths
    call ``announce_object_store`` once instead.
    """
    config = StorageConfig.from_settings(settings if settings is not None else get_settings())
    return _STORES[config.provider](config)


def announce_object_store(store: ObjectStore) -> None:
    """Log, once per process start, what storage is in use and any pre-rename variables left over."""
    describe = getattr(store, "describe", None)
    logger.info("object storage ready: %s", describe() if describe else type(store).__name__)
    leftover = legacy_env_names()
    if leftover:
        logger.warning(
            "ignoring object-storage variables from before the rename: %s", describe_legacy(leftover)
        )
