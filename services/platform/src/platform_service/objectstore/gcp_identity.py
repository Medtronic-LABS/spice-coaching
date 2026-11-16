"""Google Cloud identity of the workload: metadata-server token and service-account URL signing.

Used by ``GcsObjectStore`` when no key pair is configured (GKE Workload Identity).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from botocore.client import BaseClient
from mc_foundation.objectstore import ObjectStorageError

logger = logging.getLogger(__name__)

_METADATA_ROOT = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default"
_METADATA_TOKEN_URL = f"{_METADATA_ROOT}/token"
_METADATA_EMAIL_URL = f"{_METADATA_ROOT}/email"
_METADATA_HEADERS = {"Metadata-Flavor": "Google"}
_SIGN_BLOB_URL = "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{email}:signBlob"
# GCS rejects V4 signed URLs that live longer than seven days.
MAX_SIGNED_URL_SECONDS = 7 * 24 * 3600

TokenSource = Callable[[], str]


class GcpMetadataToken:
    """Short-lived access token from the GKE metadata server, cached until shortly before expiry."""

    def __init__(self) -> None:
        self._token = ""
        self._expiry = 0.0
        self._lock = threading.Lock()

    def __call__(self) -> str:
        with self._lock:
            now = time.monotonic()
            if self._token and now < self._expiry:
                return self._token
            request = Request(_METADATA_TOKEN_URL, headers=_METADATA_HEADERS)
            try:
                with urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode())
                token = str(payload["access_token"])
            except (OSError, KeyError, ValueError) as exc:
                raise ObjectStorageError(
                    f"could not get the workload identity token from the metadata server ({type(exc).__name__})"
                ) from exc
            expires_in = int(payload.get("expires_in") or 3600)
            self._token = token
            self._expiry = now + max(expires_in - 60, 30)
            return token


def install_bearer_token(client: BaseClient, get_token: TokenSource) -> None:
    """Send the workload's token on every request instead of an HMAC signature."""

    def _add_authorization(request: Any, **kwargs: Any) -> None:
        request.headers["Authorization"] = "Bearer " + get_token()

    client.meta.events.register("before-sign.s3", _add_authorization)


def _rfc3986(value: str) -> str:
    return quote(value, safe="-_.~")


class GcpServiceAccountSigner:
    """Sign GCS V4 download URLs as the workload's service account.

    The private key never leaves Google: the string to sign goes to the IAM ``signBlob`` API. The
    service account needs ``roles/iam.serviceAccountTokenCreator`` on itself for that call to
    succeed. Each link costs one blocking ``signBlob`` call, so it counts against the IAM
    ``signBlob`` quota; keep link batches small.
    """

    def __init__(self, get_token: TokenSource) -> None:
        self._get_token = get_token
        self._email = ""

    def service_account_email(self) -> str:
        if not self._email:
            request = Request(_METADATA_EMAIL_URL, headers=_METADATA_HEADERS)
            with urlopen(request, timeout=5) as response:
                self._email = response.read().decode().strip()
        return self._email

    def sign_blob(self, email: str, payload: bytes) -> bytes:
        body = json.dumps({"payload": base64.b64encode(payload).decode()}).encode()
        request = Request(
            _SIGN_BLOB_URL.format(email=quote(email, safe="@.")),
            data=body,
            method="POST",
            headers={"Authorization": "Bearer " + self._get_token(), "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=10) as response:
            payload_json = json.loads(response.read().decode())
        return base64.b64decode(payload_json["signedBlob"])

    def signed_get_url(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        key: str,
        expires_seconds: int,
        query: dict[str, str],
        now: datetime | None = None,
    ) -> str:
        parsed = urlparse(endpoint_url)
        host = parsed.netloc
        email = self.service_account_email()
        moment = now or datetime.now(UTC)
        stamp = moment.strftime("%Y%m%dT%H%M%SZ")
        scope = f"{moment:%Y%m%d}/auto/storage/goog4_request"
        params = dict(query)
        lifetime = min(max(expires_seconds, 1), MAX_SIGNED_URL_SECONDS)
        if lifetime != expires_seconds:
            logger.warning("signed URL lifetime clamped from %ss to %ss", expires_seconds, lifetime)
        params.update(
            {
                "X-Goog-Algorithm": "GOOG4-RSA-SHA256",
                "X-Goog-Credential": f"{email}/{scope}",
                "X-Goog-Date": stamp,
                "X-Goog-Expires": str(lifetime),
                "X-Goog-SignedHeaders": "host",
            }
        )
        canonical_query = "&".join(f"{_rfc3986(k)}={_rfc3986(v)}" for k, v in sorted(params.items()))
        path = f"/{_rfc3986(bucket)}/{quote(key, safe='/-_.~')}"
        canonical_request = "\n".join(
            ["GET", path, canonical_query, f"host:{host}", "", "host", "UNSIGNED-PAYLOAD"]
        )
        string_to_sign = "\n".join(
            [
                "GOOG4-RSA-SHA256",
                stamp,
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signature = self.sign_blob(email, string_to_sign.encode()).hex()
        return f"{parsed.scheme}://{host}{path}?{canonical_query}&X-Goog-Signature={signature}"
