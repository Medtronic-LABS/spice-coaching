"""Behaviour shared by every provider store, with a mocked boto3 client."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from mc_foundation.objectstore import ObjectNotFoundError, ObjectStorageError, ObjectTooLargeError
from platform_service.objectstore.boto_store import BotoLinkSigner, BotoObjectStore, build_boto_client

from tests.helpers.storage import storage_config


def _store(*, create_bucket: bool = False) -> BotoObjectStore:
    client = MagicMock()
    client.head_bucket.return_value = {}
    client.head_object.return_value = {}
    client.meta.region_name = "us-east-1"
    signer = BotoLinkSigner(client, "access key")
    return BotoObjectStore(
        storage_config(bucket="medtronics-storage"),
        client=client,
        link_signer=signer,
        create_bucket=create_bucket,
    )


def _client_error(code: str, operation: str = "HeadBucket") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "err"}}, operation)


# ─── uploads ────────────────────────────────────────────────────────────────


async def test_upload_file_puts_object() -> None:
    store = _store()
    stored = await store.upload_file(file_obj=BytesIO(b"hello"), filename="note.txt", prefix="uploads")
    assert stored.bucket_name == "medtronics-storage"
    assert stored.object_name.startswith("uploads/")
    assert stored.storage_path == f"medtronics-storage/{stored.object_name}"
    assert stored.size_bytes == 5
    store._client.put_object.assert_called_once()


async def test_upload_file_ascii_sanitises_non_ascii_filename() -> None:
    store = _store()
    stored = await store.upload_file(file_obj=BytesIO(b"%PDF"), filename="উচ্চরক্তচাপ.pdf", prefix="uploads")
    key = store._client.put_object.call_args.kwargs["Key"]
    assert key == stored.object_name
    key.encode("ascii")
    assert key.rsplit("/", 1)[-1].endswith("_file.pdf")


async def test_upload_file_rejects_oversized() -> None:
    store = _store()
    with pytest.raises(ObjectTooLargeError):
        await store.upload_file(
            file_obj=BytesIO(b"abcdef"), filename="big.bin", prefix="uploads", max_bytes=3
        )
    store._client.put_object.assert_not_called()


async def test_upload_file_rejects_a_prefix_outside_the_allow_list() -> None:
    with pytest.raises(ValueError, match="unsupported prefix"):
        await _store().upload_file(file_obj=BytesIO(b"x"), filename="a.txt", prefix="secrets")


async def test_put_object_from_local_file(tmp_path: Path) -> None:
    store = _store()
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF")
    stored = await store.put_object_from_local_file(
        object_name="ingest/doc.pdf",
        local_path=src,
        content_type="application/pdf",
        metadata={"sha256": "abc"},
    )
    assert stored.object_name == "ingest/doc.pdf"
    assert stored.size_bytes == 4
    store._client.upload_file.assert_called_once()


async def test_put_object_from_local_file_ascii_sanitises_key_and_metadata(tmp_path: Path) -> None:
    store = _store()
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF")
    unicode_name = "উচ্চরক্তচাপ.pdf"
    stored = await store.put_object_from_local_file(
        object_name=f"ingest/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee_{unicode_name}",
        local_path=src,
        content_type="application/pdf",
        metadata={"content-sha256": "abc", "original-filename": unicode_name},
    )
    # Unicode leaf collapses; uuid stem remains (trailing "_" stripped).
    assert stored.object_name == "ingest/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.pdf"
    call = store._client.upload_file.call_args
    assert call.args[2] == stored.object_name
    meta = call.kwargs["ExtraArgs"]["Metadata"]
    assert meta["content-sha256"] == "abc"
    assert meta["original-filename"] == quote(unicode_name, safe="")


async def test_upload_failure_is_a_storage_error(tmp_path: Path) -> None:
    store = _store()
    store._client.upload_file.side_effect = _client_error("AccessDenied", "PutObject")
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF")
    with pytest.raises(ObjectStorageError, match="failed to upload"):
        await store.put_object_from_local_file(
            object_name="ingest/doc.pdf", local_path=src, content_type="application/pdf"
        )


# ─── buckets: cloud stores never look, a MinIO that may create does ─────────


async def test_uploads_make_no_bucket_call_unless_the_store_may_create_it(tmp_path: Path) -> None:
    store = _store(create_bucket=False)
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF")
    await store.upload_file(file_obj=BytesIO(b"x"), filename="a.txt", prefix="uploads")
    await store.put_object_from_local_file(
        object_name="ingest/doc.pdf", local_path=src, content_type="application/pdf"
    )
    store._client.head_bucket.assert_not_called()
    store._client.create_bucket.assert_not_called()


async def test_creating_store_creates_a_missing_bucket_once() -> None:
    store = _store(create_bucket=True)
    store._client.head_bucket.side_effect = _client_error("404")
    await store.upload_file(file_obj=BytesIO(b"x"), filename="a.txt", prefix="uploads")
    await store.upload_file(file_obj=BytesIO(b"y"), filename="b.txt", prefix="uploads")
    store._client.create_bucket.assert_called_once_with(Bucket="medtronics-storage")
    assert store._client.head_bucket.call_count == 1


async def test_creating_store_leaves_an_existing_bucket_alone() -> None:
    store = _store(create_bucket=True)
    await store.upload_file(file_obj=BytesIO(b"x"), filename="a.txt", prefix="uploads")
    store._client.create_bucket.assert_not_called()


# ─── readiness ──────────────────────────────────────────────────────────────


async def test_check_readiness_ok_when_bucket_exists() -> None:
    store = _store()
    await store.check_readiness()
    store._client.head_bucket.assert_called_once_with(Bucket="medtronics-storage")


async def test_check_readiness_raises_on_storage_error() -> None:
    store = _store()
    store._client.head_bucket.side_effect = _client_error("AccessDenied")
    with pytest.raises(ObjectStorageError, match="readiness check failed"):
        await store.check_readiness()


async def test_check_readiness_raises_when_unreachable() -> None:
    store = _store()
    store._client.head_bucket.side_effect = EndpointConnectionError(endpoint_url="http://localhost:9000")
    with pytest.raises(ObjectStorageError, match="readiness check failed"):
        await store.check_readiness()


async def test_check_readiness_raises_when_bucket_missing() -> None:
    store = _store()
    store._client.head_bucket.side_effect = _client_error("404")
    with pytest.raises(ObjectStorageError, match="does not exist"):
        await store.check_readiness()


async def test_check_readiness_ok_when_bucket_missing_but_store_may_create_it() -> None:
    store = _store(create_bucket=True)
    store._client.head_bucket.side_effect = _client_error("NoSuchBucket")
    await store.check_readiness()


# ─── stat, links, downloads ─────────────────────────────────────────────────


async def test_stat_missing_raises() -> None:
    store = _store()
    store._client.head_object.side_effect = _client_error("404", "HeadObject")
    with pytest.raises(ObjectNotFoundError):
        await store.stat_object("uploads/missing.txt")


async def test_presigned_get_url() -> None:
    store = _store()
    store._client.generate_presigned_url.return_value = "https://example/presigned"
    result = await store.presigned_get_url(
        object_name="medtronics-storage/uploads/a.pdf",
        expires_seconds=60,
        disposition="attachment",
        download_filename="manual.pdf",
    )
    assert result.url == "https://example/presigned"
    assert result.object_name == "uploads/a.pdf"
    params = store._client.generate_presigned_url.call_args.kwargs["Params"]
    assert params == {
        "Bucket": "medtronics-storage",
        "Key": "uploads/a.pdf",
        "ResponseContentType": "application/pdf",
        "ResponseContentDisposition": 'attachment; filename="manual.pdf"',
    }


async def test_presigned_get_url_is_inline_for_viewable_types_by_default() -> None:
    store = _store()
    store._client.generate_presigned_url.return_value = "https://example/presigned"
    await store.presigned_get_url(object_name="uploads/clip.mp4", expires_seconds=60)
    params = store._client.generate_presigned_url.call_args.kwargs["Params"]
    assert params["ResponseContentDisposition"].startswith("inline;")


async def test_presigned_get_url_for_a_missing_object() -> None:
    store = _store()
    store._client.head_object.side_effect = _client_error("NoSuchKey", "HeadObject")
    with pytest.raises(ObjectNotFoundError):
        await store.presigned_get_url(object_name="uploads/a.pdf", expires_seconds=60)
    store._client.generate_presigned_url.assert_not_called()


async def test_download_maps_missing_and_other_errors(tmp_path: Path) -> None:
    store = _store()
    store._client.download_file.side_effect = _client_error("NoSuchKey", "GetObject")
    with pytest.raises(ObjectNotFoundError):
        await store.download_storage_path_to_local_file(
            storage_path="ingest/a.pdf", dest_path=tmp_path / "a.pdf"
        )
    store._client.download_file.side_effect = _client_error("AccessDenied", "GetObject")
    with pytest.raises(ObjectStorageError, match="failed to download"):
        await store.download_storage_path_to_local_file(
            storage_path="ingest/a.pdf", dest_path=tmp_path / "a.pdf"
        )


def test_describe_has_no_credentials() -> None:
    client = MagicMock()
    config = storage_config(access_key="example-access-key", secret_key="example-secret-key")
    line = BotoObjectStore(config, client=client, link_signer=BotoLinkSigner(client, "access key")).describe()
    assert line.startswith("provider=minio bucket=test-bucket endpoint=http://localhost:9000 auth=access key")
    assert line.endswith("links=access key")
    assert "example-access-key" not in line
    assert "example-secret-key" not in line


# ─── the boto3 client ───────────────────────────────────────────────────────


def test_client_only_sends_checksums_when_required() -> None:
    """boto3 1.36+ otherwise wraps uploads in aws-chunked framing that GCS stores inside the object."""
    config = build_boto_client(endpoint_url="https://storage.googleapis.com", region="auto").meta.config
    assert config.request_checksum_calculation == "when_required"
    assert config.response_checksum_validation == "when_required"


def test_client_signs_with_sigv4_and_presign_carries_no_checksum_mode() -> None:
    client = build_boto_client(
        endpoint_url="http://localhost:9000",
        region="us-east-1",
        access_key="k",
        secret_key="s",
        path_style=True,
    )
    url = client.generate_presigned_url(
        "get_object", Params={"Bucket": "b", "Key": "ingest/x.pdf"}, ExpiresIn=60
    )
    assert url.startswith("http://localhost:9000/b/ingest/x.pdf?")
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "x-amz-checksum-mode" not in url.lower()
