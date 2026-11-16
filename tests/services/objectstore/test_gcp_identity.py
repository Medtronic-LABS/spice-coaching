"""The workload's Google identity: token caching, bearer header and V4 URL signing."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
from mc_foundation.objectstore import ObjectStorageError
from platform_service.objectstore import gcp_identity
from platform_service.objectstore.gcp_identity import (
    GcpMetadataToken,
    GcpServiceAccountSigner,
    install_bearer_token,
)


def test_bearer_token_is_added_before_signing() -> None:
    # Call only our hook; emitting the full event also runs botocore's own handlers.
    client = MagicMock()
    install_bearer_token(client, lambda: "token-from-sa")
    event, handler = client.meta.events.register.call_args.args
    assert event == "before-sign.s3"
    request = MagicMock()
    request.headers = {}
    handler(request=request)
    assert request.headers["Authorization"] == "Bearer token-from-sa"


def test_metadata_token_is_cached_until_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self) -> bytes:
            calls.append(1)
            return b'{"access_token": "t%d", "expires_in": 3600}' % len(calls)

    monkeypatch.setattr(gcp_identity, "urlopen", lambda *a, **k: _Response())
    clock = [1000.0]
    monkeypatch.setattr(gcp_identity.time, "monotonic", lambda: clock[0])

    token = GcpMetadataToken()
    assert token() == "t1"
    assert token() == "t1"
    assert len(calls) == 1
    clock[0] += 3600
    assert token() == "t2"
    assert len(calls) == 2


def test_metadata_server_failure_is_a_storage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(*args: object, **kwargs: object) -> None:
        raise OSError("metadata server unreachable")

    monkeypatch.setattr(gcp_identity, "urlopen", unreachable)
    with pytest.raises(ObjectStorageError, match="workload identity token"):
        GcpMetadataToken()()


def test_signer_builds_v4_url_from_service_account() -> None:
    signed: list[bytes] = []
    signer = GcpServiceAccountSigner(lambda: "token")
    signer._email = "sa@proj.iam.gserviceaccount.com"

    def fake_sign_blob(email: str, payload: bytes) -> bytes:
        assert email == "sa@proj.iam.gserviceaccount.com"
        signed.append(payload)
        return b"\x01\xab"

    signer.sign_blob = fake_sign_blob  # type: ignore[method-assign]
    url = signer.signed_get_url(
        endpoint_url="https://storage.googleapis.com",
        bucket="leapwell-example",
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
            "/leapwell-example/ingest/a%20b.pdf",
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
        f"https://storage.googleapis.com/leapwell-example/ingest/a%20b.pdf?{canonical_query}&X-Goog-Signature=01ab"
    )


def test_signed_url_lifetime_is_clamped_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    signer = GcpServiceAccountSigner(lambda: "token")
    signer._email = "sa@proj.iam.gserviceaccount.com"
    signer.sign_blob = lambda email, payload: b"\x01"  # type: ignore[method-assign]
    with caplog.at_level("WARNING"):
        url = signer.signed_get_url(
            endpoint_url="https://storage.googleapis.com",
            bucket="b",
            key="k",
            expires_seconds=30 * 24 * 3600,
            query={},
        )
    assert parse_qs(urlparse(url).query)["X-Goog-Expires"] == [str(7 * 24 * 3600)]
    assert "clamped" in caplog.text
