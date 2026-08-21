"""Unit tests for sync storage_path object-name helpers."""

from __future__ import annotations

from platform_service.services.sync.storage_path import (
    is_batch_presign_object_name,
    sync_object_name,
)

_BUCKET = "medtronics-storage"


def test_sync_object_name_strips_bucket_prefix() -> None:
    assert sync_object_name(f"{_BUCKET}/ingest/card.png", bucket_name=_BUCKET) == "ingest/card.png"


def test_sync_object_name_passthrough_object_key() -> None:
    assert sync_object_name("ingest/card.png", bucket_name=_BUCKET) == "ingest/card.png"


def test_sync_object_name_excludes_filesystem() -> None:
    assert sync_object_name("/tmp/legacy.pdf", bucket_name=_BUCKET) is None
    assert sync_object_name("~/.cache/x.pdf", bucket_name=_BUCKET) is None


def test_sync_object_name_blank_and_none() -> None:
    assert sync_object_name(None, bucket_name=_BUCKET) is None
    assert sync_object_name("  ", bucket_name=_BUCKET) is None


def test_is_batch_presign_object_name_accepts_keys_only() -> None:
    assert is_batch_presign_object_name("ingest/card.png", bucket_name=_BUCKET)
    assert not is_batch_presign_object_name(f"{_BUCKET}/ingest/card.png", bucket_name=_BUCKET)
    assert not is_batch_presign_object_name("/tmp/legacy.pdf", bucket_name=_BUCKET)
    assert not is_batch_presign_object_name("", bucket_name=_BUCKET)
