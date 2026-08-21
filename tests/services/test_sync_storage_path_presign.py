"""SyncPresignService.get_presigned_urls_for_storage_paths — batch presign for device sync."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mc_foundation.objectstore import ObjectNotFoundError, PresignedObjectUrl
from platform_service.config import Settings
from platform_service.services.sync.presign_service import SyncPresignService

pytestmark = pytest.mark.asyncio

_BUCKET = "medtronics-storage"
_OBJECT_KEY = "ingest/card-media.png"
_OTHER_KEY = "ingest/other.png"
_BUCKET_QUALIFIED = f"{_BUCKET}/{_OBJECT_KEY}"


def _mock_storage(*, presigned_url: str = "https://minio.example/presigned") -> MagicMock:
    storage = MagicMock()
    storage.presigned_get_url = AsyncMock(
        return_value=PresignedObjectUrl(
            url=presigned_url,
            bucket_name=_BUCKET,
            object_name=_OBJECT_KEY,
            expires_seconds=86400,
        )
    )
    return storage


@pytest.mark.asyncio
async def test_presign_all_object_names_found() -> None:
    storage = _mock_storage()
    settings = Settings()

    resp = await SyncPresignService(MagicMock()).get_presigned_urls_for_storage_paths(
        storage_paths=[_OBJECT_KEY, _OTHER_KEY],
        storage=storage,
        settings=settings,
    )

    assert resp.missing_paths == []
    assert len(resp.urls) == 2
    assert resp.urls[0].storage_path == _OBJECT_KEY
    assert resp.urls[0].presigned_url == "https://minio.example/presigned"
    assert resp.urls[0].expires_seconds == settings.admin_file_presigned_max_seconds
    assert resp.urls[1].storage_path == _OTHER_KEY
    assert storage.presigned_get_url.await_count == 2


@pytest.mark.asyncio
async def test_presign_bucket_qualified_path_in_missing() -> None:
    storage = _mock_storage()

    resp = await SyncPresignService(MagicMock()).get_presigned_urls_for_storage_paths(
        storage_paths=[_BUCKET_QUALIFIED],
        storage=storage,
    )

    assert resp.urls == []
    assert resp.missing_paths == [_BUCKET_QUALIFIED]
    storage.presigned_get_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_presign_legacy_filesystem_path_in_missing() -> None:
    storage = _mock_storage()
    legacy_path = "/tmp/legacy.pdf"

    resp = await SyncPresignService(MagicMock()).get_presigned_urls_for_storage_paths(
        storage_paths=[legacy_path],
        storage=storage,
    )

    assert resp.urls == []
    assert resp.missing_paths == [legacy_path]
    storage.presigned_get_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_presign_missing_object_in_missing_paths() -> None:
    storage = _mock_storage()
    storage.presigned_get_url = AsyncMock(side_effect=ObjectNotFoundError("missing"))

    resp = await SyncPresignService(MagicMock()).get_presigned_urls_for_storage_paths(
        storage_paths=[_OBJECT_KEY],
        storage=storage,
    )

    assert resp.urls == []
    assert resp.missing_paths == [_OBJECT_KEY]


@pytest.mark.asyncio
async def test_presign_mixed_batch_partial_success() -> None:
    storage = _mock_storage()
    legacy_path = "/tmp/legacy.pdf"

    async def _presign_side_effect(*, object_name: str, **kwargs):  # type: ignore[no-untyped-def]
        if object_name == _OTHER_KEY:
            raise ObjectNotFoundError("missing")
        return PresignedObjectUrl(
            url="https://minio.example/presigned",
            bucket_name=_BUCKET,
            object_name=_OBJECT_KEY,
            expires_seconds=86400,
        )

    storage.presigned_get_url = AsyncMock(side_effect=_presign_side_effect)

    resp = await SyncPresignService(MagicMock()).get_presigned_urls_for_storage_paths(
        storage_paths=[_OBJECT_KEY, legacy_path, _OTHER_KEY, _BUCKET_QUALIFIED],
        storage=storage,
    )

    assert len(resp.urls) == 1
    assert resp.urls[0].storage_path == _OBJECT_KEY
    assert resp.missing_paths == [legacy_path, _OTHER_KEY, _BUCKET_QUALIFIED]


@pytest.mark.asyncio
async def test_presign_empty_string_path_in_missing() -> None:
    storage = _mock_storage()

    resp = await SyncPresignService(MagicMock()).get_presigned_urls_for_storage_paths(
        storage_paths=[""],
        storage=storage,
    )

    assert resp.urls == []
    assert resp.missing_paths == [""]
    storage.presigned_get_url.assert_not_awaited()
