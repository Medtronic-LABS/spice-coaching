"""Unit tests for ``S3ObjectStore`` upload / presign with mocked boto3."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs, quote, urlparse

import pytest
from botocore import UNSIGNED
from botocore.exceptions import ClientError
from mc_foundation.objectstore import ObjectNotFoundError, ObjectStorageError, ObjectTooLargeError
from platform_service.objectstore.s3_store import S3ObjectStore, _GcpServiceAccountSigner, _install_gcp_bearer


def _store() -> S3ObjectStore:
    store = S3ObjectStore(
        endpoint="localhost:9000",
        access_key="k",
        secret_key="s",
        bucket_name="medtronics-storage",
        backend="minio",
        secure=False,
        allowed_prefixes=frozenset({"uploads", "ingest"}),
        auto_create_bucket=True,
    )
    store._client = MagicMock()
    store._presign_client = store._client
    store._client.head_bucket.return_value = {}
    return store


@pytest.mark.asyncio
async def test_upload_file_puts_object() -> None:
    store = _store()
    stored = await store.upload_file(
        file_obj=BytesIO(b"hello"),
        filename="note.txt",
        prefix="uploads",
    )
    assert stored.bucket_name == "medtronics-storage"
    assert stored.object_name.startswith("uploads/")
    assert stored.size_bytes == 5
    store._client.put_object.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_ascii_sanitises_non_ascii_filename() -> None:
    store = _store()
    stored = await store.upload_file(
        file_obj=BytesIO(b"%PDF"),
        filename="উচ্চরক্তচাপ.pdf",
        prefix="uploads",
    )
    key = store._client.put_object.call_args.kwargs["Key"]
    assert key == stored.object_name
    assert key.startswith("uploads/")
    assert key.endswith(".pdf")
    key.encode("ascii")
    assert "উচ্চ" not in key
    leaf = key.rsplit("/", 1)[-1]
    assert "_" in leaf
    assert leaf.endswith("_file.pdf")


@pytest.mark.asyncio
async def test_upload_file_rejects_oversized() -> None:
    store = _store()
    with pytest.raises(ObjectTooLargeError):
        await store.upload_file(
            file_obj=BytesIO(b"abcdef"),
            filename="big.bin",
            prefix="uploads",
            max_bytes=3,
        )


@pytest.mark.asyncio
async def test_presigned_get_url() -> None:
    store = _store()
    store._client.head_object.return_value = {}
    store._presign_client.generate_presigned_url.return_value = "https://example/presigned"

    result = await store.presigned_get_url(
        object_name="uploads/a.pdf",
        expires_seconds=60,
        disposition="attachment",
        download_filename="manual.pdf",
    )
    assert result.url == "https://example/presigned"
    assert result.object_name == "uploads/a.pdf"
    store._presign_client.generate_presigned_url.assert_called_once()


@pytest.mark.asyncio
async def test_stat_missing_raises() -> None:
    store = _store()
    store._client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "missing"}},
        "HeadObject",
    )
    with pytest.raises(ObjectNotFoundError):
        await store.stat_object("uploads/missing.txt")


@pytest.mark.asyncio
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
    store._client.upload_file.assert_called_once()


@pytest.mark.asyncio
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
    stored.object_name.encode("ascii")
    # Unicode leaf collapses; uuid stem remains (trailing "_" stripped).
    assert stored.object_name == "ingest/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.pdf"
    call_kwargs = store._client.upload_file.call_args
    assert call_kwargs.args[2] == stored.object_name
    meta = call_kwargs.kwargs["ExtraArgs"]["Metadata"]
    assert meta["content-sha256"] == "abc"
    assert meta["original-filename"] == quote(unicode_name, safe="")
    meta["original-filename"].encode("ascii")


def test_gcp_auth_uses_pod_service_account(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "platform_service.objectstore.s3_store._GcpMetadataToken.__call__",
        lambda self: "token-from-sa",
    )
    store = S3ObjectStore(
        endpoint="storage.googleapis.com",
        access_key="",
        secret_key="",
        bucket_name="leapwell-micro-coaching",
        backend="minio",
        secure=True,
        region="auto",
        auth="gcp",
        auto_create_bucket=False,
    )
    assert store._auth == "gcp"
    assert store._client.meta.config.signature_version is UNSIGNED
    store.close()

    # Call only our hook; emitting the full event also runs botocore's own handlers.
    client = MagicMock()
    _install_gcp_bearer(client)
    event, handler = client.meta.events.register.call_args.args
    assert event == "before-sign.s3"
    request = MagicMock()
    request.headers = {}
    handler(request=request)
    assert request.headers["Authorization"] == "Bearer token-from-sa"


def test_client_only_sends_checksums_when_required() -> None:
    store = S3ObjectStore(
        endpoint="storage.googleapis.com",
        access_key="k",
        secret_key="s",
        bucket_name="leapwell-micro-coaching",
        backend="minio",
        region="auto",
    )
    config = store._client.meta.config
    assert config.request_checksum_calculation == "when_required"
    assert config.response_checksum_validation == "when_required"
    store.close()


def _gcp_store_without_hmac(monkeypatch: pytest.MonkeyPatch) -> S3ObjectStore:
    monkeypatch.setattr(
        "platform_service.objectstore.s3_store._GcpMetadataToken.__call__",
        lambda self: "token-from-sa",
    )
    store = S3ObjectStore(
        endpoint="storage.googleapis.com",
        access_key="",
        secret_key="",
        bucket_name="leapwell-micro-coaching",
        backend="minio",
        region="auto",
        auth="gcp",
        allowed_prefixes=frozenset({"ingest"}),
    )
    store._client = MagicMock()
    store._client.head_object.return_value = {}
    return store


def test_gcp_signer_builds_v4_url_from_service_account() -> None:
    signed: list[bytes] = []
    signer = _GcpServiceAccountSigner(lambda: "token")
    signer._email = "sa@proj.iam.gserviceaccount.com"

    def fake_sign_blob(email: str, payload: bytes) -> bytes:
        assert email == "sa@proj.iam.gserviceaccount.com"
        signed.append(payload)
        return b"\x01\xab"

    signer.sign_blob = fake_sign_blob  # type: ignore[method-assign]
    url = signer.signed_get_url(
        endpoint_url="https://storage.googleapis.com",
        bucket="leapwell-micro-coaching",
        key="ingest/a b.pdf",
        expires_seconds=3600,
        query={"response-content-type": "application/pdf"},
        now=datetime(2026, 10, 28, 9, 30, 0, tzinfo=UTC),
    )

    canonical_query = (
        "X-Goog-Algorithm=GOOG4-RSA-SHA256"
        "&X-Goog-Credential=sa%40proj.iam.gserviceaccount.com%2F20261028%2Fauto%2Fstorage%2Fgoog4_request"
        "&X-Goog-Date=20261028T093000Z&X-Goog-Expires=3600&X-Goog-SignedHeaders=host"
        "&response-content-type=application%2Fpdf"
    )
    canonical_request = "\n".join(
        [
            "GET",
            "/leapwell-micro-coaching/ingest/a%20b.pdf",
            canonical_query,
            "host:storage.googleapis.com",
            "",
            "host",
            "UNSIGNED-PAYLOAD",
        ]
    )
    expected_string_to_sign = "\n".join(
        [
            "GOOG4-RSA-SHA256",
            "20261028T093000Z",
            "20261028/auto/storage/goog4_request",
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    assert signed == [expected_string_to_sign.encode()]
    assert url == (
        "https://storage.googleapis.com/leapwell-micro-coaching/ingest/a%20b.pdf?"
        f"{canonical_query}&X-Goog-Signature=01ab"
    )


@pytest.mark.asyncio
async def test_gcp_auth_without_hmac_signs_links_with_service_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _gcp_store_without_hmac(monkeypatch)
    assert store._gcp_signer is not None
    store._gcp_signer._email = "sa@proj.iam.gserviceaccount.com"
    store._gcp_signer.sign_blob = lambda email, payload: b"\xff"  # type: ignore[method-assign]

    result = await store.presigned_get_url(
        object_name="leapwell-micro-coaching/ingest/doc.pdf",
        expires_seconds=600,
        disposition="inline",
        download_filename=None,
    )

    parsed = urlparse(result.url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "storage.googleapis.com"
    assert parsed.path == "/leapwell-micro-coaching/ingest/doc.pdf"
    assert query["X-Goog-Algorithm"] == ["GOOG4-RSA-SHA256"]
    assert query["X-Goog-Expires"] == ["600"]
    assert query["X-Goog-Signature"] == ["ff"]
    assert query["response-content-type"] == ["application/pdf"]
    store._client.generate_presigned_url.assert_not_called()


def test_gcp_auth_with_hmac_keeps_hmac_presign(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "platform_service.objectstore.s3_store._GcpMetadataToken.__call__",
        lambda self: "token-from-sa",
    )
    store = S3ObjectStore(
        endpoint="storage.googleapis.com",
        access_key="k",
        secret_key="s",
        bucket_name="leapwell-micro-coaching",
        backend="minio",
        region="auto",
        auth="gcp",
    )
    assert store._gcp_signer is None
    assert store._presign_client is not store._client
    store.close()


@pytest.mark.asyncio
async def test_gcp_signing_failure_raises_storage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _gcp_store_without_hmac(monkeypatch)
    assert store._gcp_signer is not None
    store._gcp_signer._email = "sa@proj.iam.gserviceaccount.com"

    def denied(email: str, payload: bytes) -> bytes:
        raise OSError("HTTP Error 403: Forbidden")

    store._gcp_signer.sign_blob = denied  # type: ignore[method-assign]
    with pytest.raises(ObjectStorageError):
        await store.presigned_get_url(
            object_name="ingest/doc.pdf",
            expires_seconds=600,
            disposition="inline",
            download_filename=None,
        )
