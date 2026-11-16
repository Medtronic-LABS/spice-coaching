"""What differs per provider: how the client authenticates, addresses buckets and signs links.

No network: clients are real boto3 clients, and where a request is sent the HTTP layer is stubbed.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from botocore import UNSIGNED
from botocore.awsrequest import AWSResponse
from mc_foundation.objectstore import ObjectStorageError
from platform_service.objectstore import boto_store, gcp_identity
from platform_service.objectstore.boto_store import BotoLinkSigner, BotoObjectStore
from platform_service.objectstore.gcs_store import GcsObjectStore, ServiceAccountLinkSigner
from platform_service.objectstore.minio_store import MinioObjectStore
from platform_service.objectstore.s3_store import S3ObjectStore

from tests.helpers.storage import storage_config

KEYLESS = {"access_key": "", "secret_key": ""}


@pytest.fixture
def workload_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the GKE metadata server."""
    monkeypatch.setattr(gcp_identity.GcpMetadataToken, "__call__", lambda self: "token-from-sa")


class _Raw:
    def stream(self, amt: int = 1024, decode_content: bool | None = None):
        return iter(())

    def read(self, amt: int | None = None) -> bytes:
        return b""


def _capture_requests(store: BotoObjectStore) -> list[tuple[str, str, dict[str, str], bytes]]:
    """Answer every request with 200 and record (method, url, headers, body as sent)."""
    sent: list[tuple[str, str, dict[str, str], bytes]] = []

    def handler(request: Any, **kwargs: Any) -> AWSResponse:
        body = request.body
        data = body.read() if hasattr(body, "read") else (body or b"")
        headers = {str(k).lower(): _text(v) for k, v in request.headers.items()}
        sent.append((request.method, request.url, headers, data))
        return AWSResponse(request.url, 200, {"ETag": '"stub"'}, _Raw())

    store._client.meta.events.register("before-send.s3", handler)
    return sent


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _link(store: BotoObjectStore, key: str = "ingest/a.pdf") -> str:
    return store._link_signer.sign_get(
        bucket=store.bucket_name,
        key=key,
        expires_seconds=60,
        content_type="application/pdf",
        disposition="inline",
    )


# ─── every provider stores the bytes it was given ───────────────────────────


@pytest.mark.parametrize(
    "store_factory",
    [
        lambda: MinioObjectStore(storage_config("minio")),
        lambda: S3ObjectStore(storage_config("s3")),
        lambda: GcsObjectStore(storage_config("gcs")),
        lambda: GcsObjectStore(storage_config("gcs", **KEYLESS)),
    ],
    ids=["minio", "s3", "gcs-key", "gcs-attached-identity"],
)
async def test_upload_is_sent_byte_for_byte(store_factory: Any, tmp_path: Path, workload_token: None) -> None:
    """Regression: aws-chunked framing with a CRC32 trailer ended up inside GCS objects."""
    store = store_factory()
    sent = _capture_requests(store)
    payload = b"%PDF-1.4\n" + b"x" * 600 + b"\n%%EOF\n"
    src = tmp_path / "doc.pdf"
    src.write_bytes(payload)

    await store.put_object_from_local_file(
        object_name="ingest/doc.pdf", local_path=src, content_type="application/pdf"
    )
    await store.upload_file(file_obj=io.BytesIO(payload), filename="doc.pdf", prefix="uploads")

    puts = [item for item in sent if item[0] == "PUT"]
    assert len(puts) == 2
    for _method, _url, headers, body in puts:
        assert body == payload
        assert "content-encoding" not in headers
        assert "x-amz-trailer" not in headers
    assert [item[0] for item in sent if item[0] != "PUT"] == [], "no bucket call before an upload"


# ─── minio ──────────────────────────────────────────────────────────────────


def test_minio_signs_path_style_links_with_its_key() -> None:
    store = MinioObjectStore(storage_config("minio", bucket="dev-bucket"))
    url = urlparse(_link(store))
    assert (url.scheme, url.netloc, url.path) == ("http", "localhost:9000", "/dev-bucket/ingest/a.pdf")
    assert parse_qs(url.query)["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert store._link_signer.description == "access key"


def test_minio_links_use_the_public_endpoint_and_data_calls_do_not() -> None:
    store = MinioObjectStore(storage_config("minio", public_endpoint="https://files.example.org"))
    assert urlparse(_link(store)).netloc == "files.example.org"
    assert store._client.meta.endpoint_url == "http://localhost:9000"


@pytest.mark.parametrize("create_bucket", [True, False])
def test_minio_is_the_only_store_that_may_create_a_bucket(create_bucket: bool) -> None:
    assert (
        MinioObjectStore(storage_config("minio", create_bucket=create_bucket))._create_bucket is create_bucket
    )
    # Even if a config carrying create_bucket reached them (validation forbids it), they ignore it.
    assert S3ObjectStore(storage_config("s3", create_bucket=True))._create_bucket is False
    assert GcsObjectStore(storage_config("gcs", create_bucket=True))._create_bucket is False


# ─── s3 ─────────────────────────────────────────────────────────────────────


def test_s3_uses_the_regional_aws_endpoint_and_its_key() -> None:
    store = S3ObjectStore(storage_config("s3", bucket="prod-bucket", region="ap-south-1"))
    url = urlparse(_link(store))
    # Virtual-hosted style on AWS's own host (boto3 picks the exact host); the region is in the scope.
    assert url.netloc.startswith("prod-bucket.s3.") and url.netloc.endswith("amazonaws.com")
    assert url.path == "/ingest/a.pdf"
    assert "ap-south-1" in parse_qs(url.query)["X-Amz-Credential"][0]


def test_s3_without_keys_leaves_credentials_to_the_aws_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    real_client = boto_store.boto3.client

    def recording_client(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return real_client(**kwargs)

    monkeypatch.setattr(boto_store.boto3, "client", recording_client)
    store = S3ObjectStore(storage_config("s3", **KEYLESS))
    assert calls, "a client was built"
    for kwargs in calls:
        assert "aws_access_key_id" not in kwargs
        assert "aws_secret_access_key" not in kwargs
    assert store._client.meta.config.signature_version == "s3v4"
    assert store._link_signer.description == "attached workload identity"

    S3ObjectStore(storage_config("s3", access_key="example-access-key", secret_key="example-secret-key"))
    assert calls[-1]["aws_access_key_id"] == "example-access-key"


# ─── gcs with a key pair ────────────────────────────────────────────────────


def test_gcs_with_a_key_signs_data_calls_and_links_with_it(tmp_path: Path) -> None:
    store = GcsObjectStore(storage_config("gcs", bucket="leapwell-example"))
    assert isinstance(store._link_signer, BotoLinkSigner)
    assert store._link_signer.description == "HMAC key"
    url = urlparse(_link(store))
    assert (url.netloc, url.path) == ("storage.googleapis.com", "/leapwell-example/ingest/a.pdf")
    assert parse_qs(url.query)["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]

    sent = _capture_requests(store)
    store._client.head_object(Bucket="leapwell-example", Key="ingest/a.pdf")
    assert sent[0][2]["authorization"].startswith("AWS4-HMAC-SHA256 ")


def test_gcs_key_links_can_go_through_a_public_endpoint() -> None:
    store = GcsObjectStore(storage_config("gcs", public_endpoint="https://files.example.org"))
    assert urlparse(_link(store)).netloc == "files.example.org"


# ─── gcs with the attached service account ──────────────────────────────────


def test_gcs_without_keys_sends_the_workload_token(workload_token: None) -> None:
    store = GcsObjectStore(storage_config("gcs", bucket="leapwell-example", **KEYLESS))
    assert store._client.meta.config.signature_version is UNSIGNED
    sent = _capture_requests(store)
    store._client.head_object(Bucket="leapwell-example", Key="ingest/a.pdf")
    _method, url, headers, _body = sent[0]
    assert headers["authorization"] == "Bearer token-from-sa"
    assert url == "https://storage.googleapis.com/leapwell-example/ingest/a.pdf"


async def test_gcs_without_keys_signs_links_as_the_service_account(workload_token: None) -> None:
    store = GcsObjectStore(storage_config("gcs", bucket="leapwell-example", **KEYLESS))
    signer = store._link_signer
    assert isinstance(signer, ServiceAccountLinkSigner)
    signer._signer._email = "sa@proj.iam.gserviceaccount.com"
    signer._signer.sign_blob = lambda email, payload: b"\xff"  # type: ignore[method-assign]
    _capture_requests(store)

    result = await store.presigned_get_url(
        object_name="leapwell-example/ingest/doc.pdf", expires_seconds=600, disposition="inline"
    )

    parsed = urlparse(result.url)
    query = parse_qs(parsed.query)
    assert (parsed.netloc, parsed.path) == ("storage.googleapis.com", "/leapwell-example/ingest/doc.pdf")
    assert query["X-Goog-Algorithm"] == ["GOOG4-RSA-SHA256"]
    assert query["X-Goog-Credential"][0].startswith("sa@proj.iam.gserviceaccount.com/")
    assert query["X-Goog-Expires"] == ["600"]
    assert query["X-Goog-Signature"] == ["ff"]
    assert query["response-content-type"] == ["application/pdf"]
    assert "links=attached service account" in store.describe()


async def test_gcs_signing_failure_is_a_storage_error(workload_token: None) -> None:
    """E.g. the service account lacks Token Creator on itself."""
    store = GcsObjectStore(storage_config("gcs", **KEYLESS))
    signer = store._link_signer
    assert isinstance(signer, ServiceAccountLinkSigner)
    signer._signer._email = "sa@proj.iam.gserviceaccount.com"

    def denied(email: str, payload: bytes) -> bytes:
        raise OSError("HTTP Error 403: Forbidden")

    signer._signer.sign_blob = denied  # type: ignore[method-assign]
    _capture_requests(store)
    with pytest.raises(ObjectStorageError, match="failed to generate presigned URL"):
        await store.presigned_get_url(object_name="ingest/doc.pdf", expires_seconds=600)
