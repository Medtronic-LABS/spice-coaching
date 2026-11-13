"""boto3-backed ObjectStore for MinIO and AWS S3."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import threading
import time
import unicodedata
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Literal, get_args
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import anyio
import boto3
from botocore import UNSIGNED
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from mc_foundation.objectstore import (
    ContentDisposition,
    ObjectNotFoundError,
    ObjectStorageError,
    ObjectTooLargeError,
    PresignedObjectUrl,
    StoredObject,
    content_type_for,
    normalise_prefix,
    resolve_object_name,
    safe_basename,
)

logger = logging.getLogger(__name__)

ObjectStorageBackend = Literal["minio", "s3"]
ObjectStorageAuth = Literal["hmac", "gcp"]
PresignMode = Literal["direct", "proxy"]
_GCP_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
_GCP_METADATA_EMAIL_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
)
_GCP_SIGN_BLOB_URL = "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{email}:signBlob"
_GCS_DEFAULT_ENDPOINT = "https://storage.googleapis.com"
# GCS rejects V4 signed URLs that live longer than seven days.
_GCS_MAX_SIGNED_URL_SECONDS = 7 * 24 * 3600

_UNSAFE_KEY_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_ASCII_EXT = re.compile(r"^[A-Za-z0-9]{1,10}$")


def _ascii_safe_object_basename(name: str) -> str:
    """Basename safe for S3 object keys and SigV4 HTTP headers (ASCII only)."""
    base = safe_basename(name)
    stem, dot, ext = base.rpartition(".")
    if not stem or not dot or not _ASCII_EXT.fullmatch(ext):
        stem, ext = base, ""
    else:
        ext = f".{ext}"

    normalised = unicodedata.normalize("NFKD", stem)
    ascii_stem = normalised.encode("ascii", "ignore").decode("ascii")
    ascii_stem = _UNSAFE_KEY_CHARS.sub("_", ascii_stem).strip("._") or "file"
    ascii_ext = ext.encode("ascii", "ignore").decode("ascii")
    ascii_ext = re.sub(r"[^A-Za-z0-9.]", "", ascii_ext)
    return f"{ascii_stem}{ascii_ext}"


def _ascii_safe_object_key(object_name: str) -> str:
    """Keep path prefixes; ASCII-sanitise only the final key segment."""
    parts = object_name.split("/")
    parts[-1] = _ascii_safe_object_basename(parts[-1])
    return "/".join(parts)


def _ascii_safe_metadata(metadata: dict[str, str]) -> dict[str, str]:
    """Percent-encode non-ASCII metadata values (S3 user metadata is ASCII-only)."""
    out: dict[str, str] = {}
    for key, value in metadata.items():
        text = str(value)
        try:
            text.encode("ascii")
        except UnicodeEncodeError:
            text = quote(text, safe="")
        out[str(key)] = text
    return out


def _endpoint_url(endpoint: str | None, *, secure: bool) -> str | None:
    if not endpoint or not endpoint.strip():
        return None
    raw = endpoint.strip()
    explicit_scheme = "://" in raw
    parsed = urlparse(raw if explicit_scheme else f"{'https' if secure else 'http'}://{raw}")
    if parsed.path not in ("", "/"):
        raise ValueError("object storage endpoint must not include a path")
    if not parsed.netloc:
        raise ValueError("object storage endpoint is invalid")
    # Honor an explicit scheme (e.g. https:// in presigned_endpoint) even when secure=False.
    # Bare hostnames (no "://") fall back to the secure flag.
    scheme = parsed.scheme if explicit_scheme else ("https" if secure else "http")
    return f"{scheme}://{parsed.netloc}"


def _content_disposition_for(object_name: str, *, inline: bool, download_filename: str | None = None) -> str:
    filename = (download_filename or PurePosixPath(object_name).name).strip()
    if not filename:
        filename = PurePosixPath(object_name).name
    disp = "inline" if inline else "attachment"
    try:
        filename.encode("ascii")
    except UnicodeEncodeError:
        return f"{disp}; filename*=UTF-8''{quote(filename)}"
    return f'{disp}; filename="{filename}"'


def _inline_default_for_content_type(content_type: str) -> bool:
    if content_type == "application/pdf":
        return True
    return content_type.startswith(("image/", "video/", "audio/"))


def _is_not_found(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code", "")
    return code in {
        "404",
        "NoSuchBucket",
        "NoSuchKey",
        "NotFound",
        "404 Not Found",
    }


class _GcpMetadataToken:
    """Short-lived access token from the GKE metadata server."""

    def __init__(self) -> None:
        self._token = ""
        self._expiry = 0.0
        self._lock = threading.Lock()

    def __call__(self) -> str:
        with self._lock:
            now = time.monotonic()
            if self._token and now < self._expiry:
                return self._token
            request = Request(_GCP_METADATA_TOKEN_URL, headers={"Metadata-Flavor": "Google"})
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode())
            token = str(payload["access_token"])
            expires_in = int(payload.get("expires_in") or 3600)
            self._token = token
            self._expiry = now + max(expires_in - 60, 30)
            return token


def _install_gcp_bearer(client: BaseClient, get_token: Callable[[], str]) -> None:
    """Send the pod service-account token instead of an HMAC signature."""

    def _add_authorization(request: Any, **kwargs: Any) -> None:
        request.headers["Authorization"] = "Bearer " + get_token()

    client.meta.events.register("before-sign.s3", _add_authorization)


def _rfc3986(value: str) -> str:
    return quote(value, safe="-_.~")


class _GcpServiceAccountSigner:
    """Sign GCS V4 download URLs with the pod service account.

    The private key never leaves Google: the string to sign goes to the IAM
    ``signBlob`` API. The service account needs ``roles/iam.serviceAccountTokenCreator``
    on itself for that call to succeed. Each link costs one blocking ``signBlob``
    call, so it counts against the IAM ``signBlob`` quota; keep link batches small.
    """

    def __init__(self, get_token: Callable[[], str]) -> None:
        self._get_token = get_token
        self._email = ""

    def service_account_email(self) -> str:
        if not self._email:
            request = Request(_GCP_METADATA_EMAIL_URL, headers={"Metadata-Flavor": "Google"})
            with urlopen(request, timeout=5) as response:
                self._email = response.read().decode().strip()
        return self._email

    def sign_blob(self, email: str, payload: bytes) -> bytes:
        body = json.dumps({"payload": base64.b64encode(payload).decode()}).encode()
        request = Request(
            _GCP_SIGN_BLOB_URL.format(email=quote(email, safe="@.")),
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
        lifetime = min(max(expires_seconds, 1), _GCS_MAX_SIGNED_URL_SECONDS)
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


def _build_s3_client(
    *,
    endpoint_url: str | None,
    region: str,
    access_key: str,
    secret_key: str,
    addressing_style: Literal["auto", "path"] = "auto",
    auth: ObjectStorageAuth = "hmac",
    get_token: Callable[[], str] | None = None,
) -> BaseClient:
    # AWS S3 rejects SigV2; always force AWS4-HMAC-SHA256 for uploads and presigns.
    # GCP auth skips signing and uses the pod service-account bearer token.
    # boto3 1.36+ sends uploads as aws-chunked with a CRC32 trailer by default.
    # GCS and older MinIO store that framing inside the object, so only send
    # checksums when the API requires them.
    s3_config: dict[str, str] = {}
    if addressing_style == "path":
        s3_config["addressing_style"] = "path"
    kwargs: dict[str, Any] = {
        "service_name": "s3",
        "region_name": region or None,
        "config": Config(
            signature_version=UNSIGNED if auth == "gcp" else "s3v4",
            s3=s3_config,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if auth != "gcp" and access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    client = boto3.client(**kwargs)
    if auth == "gcp":
        if get_token is None:
            raise ValueError("get_token is required when auth='gcp'")
        _install_gcp_bearer(client, get_token)
    return client


class S3ObjectStore:
    """Async wrapper around a sync boto3 S3 client (MinIO or AWS)."""

    def __init__(
        self,
        *,
        bucket_name: str,
        region: str = "us-east-1",
        endpoint: str | None = None,
        presigned_endpoint: str | None = None,
        access_key: str = "",
        secret_key: str = "",
        secure: bool = True,
        backend: ObjectStorageBackend = "s3",
        presign_mode: PresignMode = "direct",
        allowed_prefixes: frozenset[str] | None = None,
        auto_create_bucket: bool = False,
        auth: ObjectStorageAuth = "hmac",
    ) -> None:
        self.bucket_name = bucket_name
        self.allowed_prefixes = allowed_prefixes or frozenset({"uploads"})
        self._backend = backend
        self._presign_mode = presign_mode
        if auth not in get_args(ObjectStorageAuth):
            raise ValueError(
                f"unsupported OBJECT_STORAGE_AUTH={auth!r}; supported: {get_args(ObjectStorageAuth)}"
            )
        self._auth = auth
        self._gcp_token = _GcpMetadataToken() if auth == "gcp" else None
        self._gcp_signer: _GcpServiceAccountSigner | None = None
        # Auto-create is only allowed for local MinIO; never against AWS.
        self._auto_create_bucket = auto_create_bucket if backend == "minio" else False
        self._bucket_ready = False

        data_endpoint = _endpoint_url(endpoint, secure=secure)
        self._data_endpoint = data_endpoint
        if backend == "minio" and not data_endpoint:
            raise ValueError("OBJECT_STORAGE_ENDPOINT is required when OBJECT_STORAGE_BACKEND=minio")
        if self._auth != "gcp" and backend == "minio" and (not access_key or not secret_key):
            raise ValueError(
                "OBJECT_STORAGE_ACCESS_KEY and OBJECT_STORAGE_SECRET_KEY are required "
                "when OBJECT_STORAGE_BACKEND=minio"
            )

        addressing: Literal["auto", "path"] = "path" if backend == "minio" or self._auth == "gcp" else "auto"
        self._client = _build_s3_client(
            endpoint_url=data_endpoint,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            addressing_style=addressing,
            auth=self._auth,
            get_token=self._gcp_token,
        )
        if self._auth == "gcp":
            logger.info("object storage calls will use the pod GCP service account")

        if presign_mode == "proxy" and self._auth == "gcp" and not (access_key and secret_key):
            raise ValueError(
                "OBJECT_STORAGE_PRESIGN_MODE=proxy with OBJECT_STORAGE_AUTH=gcp requires an HMAC key"
            )
        if presign_mode == "proxy":
            proxy_endpoint = _endpoint_url(presigned_endpoint or endpoint, secure=secure)
            self._presign_client = _build_s3_client(
                endpoint_url=proxy_endpoint,
                region=region,
                access_key=access_key,
                secret_key=secret_key,
                addressing_style=addressing,
            )
        elif self._auth == "gcp" and access_key and secret_key:
            # Download links still need an HMAC signature. Data calls use the service account.
            self._presign_client = _build_s3_client(
                endpoint_url=data_endpoint,
                region=region,
                access_key=access_key,
                secret_key=secret_key,
                addressing_style=addressing,
            )
        elif self._auth == "gcp":
            # No HMAC key: sign download links with the pod service account instead.
            self._presign_client = self._client
            self._gcp_signer = _GcpServiceAccountSigner(self._gcp_token)  # type: ignore[arg-type]
            logger.info("download links will be signed by the pod GCP service account")
        else:
            self._presign_client = self._client

    def close(self) -> None:
        """Drop client references so connection pools can be reclaimed."""
        self._presign_client = None  # type: ignore[assignment]
        self._client = None  # type: ignore[assignment]

    def object_name_from_reference(self, object_reference: str) -> str:
        return resolve_object_name(
            object_reference,
            bucket_name=self.bucket_name,
            allowed_prefixes=self.allowed_prefixes,
        )

    async def upload_file(
        self,
        *,
        file_obj: BinaryIO,
        filename: str,
        prefix: str = "uploads",
        max_bytes: int | None = None,
    ) -> StoredObject:
        return await anyio.to_thread.run_sync(
            self._upload_file_sync,
            file_obj,
            filename,
            prefix,
            max_bytes,
        )

    async def stat_object(self, object_name: str) -> None:
        await anyio.to_thread.run_sync(self._stat_object_sync, object_name)

    async def presigned_get_url(
        self,
        *,
        object_name: str,
        expires_seconds: int,
        disposition: ContentDisposition = "auto",
        download_filename: str | None = None,
    ) -> PresignedObjectUrl:
        return await anyio.to_thread.run_sync(
            self._presigned_get_url_sync,
            object_name,
            expires_seconds,
            disposition,
            download_filename,
        )

    async def put_object_from_local_file(
        self,
        *,
        object_name: str,
        local_path: Path | str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        return await anyio.to_thread.run_sync(
            self._put_object_from_local_file_sync,
            object_name,
            str(local_path),
            content_type,
            metadata,
        )

    async def download_storage_path_to_local_file(self, *, storage_path: str, dest_path: Path) -> None:
        object_name = self.object_name_from_reference(storage_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        def _download() -> None:
            try:
                self._client.download_file(self.bucket_name, object_name, str(dest_path))
            except ClientError as exc:
                if _is_not_found(exc):
                    raise ObjectNotFoundError(f"object {object_name!r} was not found") from exc
                raise ObjectStorageError(f"failed to download object {object_name!r}") from exc
            except BotoCoreError as exc:
                raise ObjectStorageError(f"failed to download object {object_name!r}") from exc

        await anyio.to_thread.run_sync(_download)

    async def check_readiness(self) -> None:
        await anyio.to_thread.run_sync(self._check_readiness_sync)

    def _stat_object_sync(self, object_name: str) -> None:
        normalised = self.object_name_from_reference(object_name)
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=normalised)
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError(f"object {normalised!r} was not found") from exc
            raise ObjectStorageError(f"failed to stat object {normalised!r}") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError(f"failed to stat object {normalised!r}") from exc

    def _upload_file_sync(
        self,
        file_obj: BinaryIO,
        filename: str,
        prefix: str,
        max_bytes: int | None,
    ) -> StoredObject:
        safe_filename = _ascii_safe_object_basename(filename)
        normalised_prefix = normalise_prefix(prefix)
        if normalised_prefix.split("/", maxsplit=1)[0] not in self.allowed_prefixes:
            raise ValueError(f"unsupported prefix {prefix!r}; accepted: {sorted(self.allowed_prefixes)}")
        object_name = f"{normalised_prefix}/{uuid.uuid4()}_{safe_filename}"
        resolved_content_type = content_type_for(safe_filename)

        try:
            self._ensure_bucket()
            file_obj.seek(0, 2)
            size_bytes = file_obj.tell()
            if max_bytes is not None and size_bytes > max_bytes:
                raise ObjectTooLargeError(f"object size {size_bytes} exceeds max {max_bytes}")
            file_obj.seek(0)
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=object_name,
                Body=file_obj,
                ContentType=resolved_content_type,
                ContentLength=size_bytes,
            )
        except ObjectTooLargeError:
            raise
        except ClientError as exc:
            raise ObjectStorageError(f"failed to upload object {object_name!r}") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError(f"failed to upload object {object_name!r}") from exc

        return StoredObject(
            bucket_name=self.bucket_name,
            object_name=object_name,
            storage_path=f"{self.bucket_name}/{object_name}",
            content_type=resolved_content_type,
            size_bytes=size_bytes,
        )

    def _put_object_from_local_file_sync(
        self,
        object_name: str,
        local_path: str,
        content_type: str,
        metadata: dict[str, str] | None,
    ) -> StoredObject:
        parts = object_name.split("/")
        if any(p in ("", ".", "..") or "\\" in p for p in parts):
            raise ValueError("object_name contains an unsafe path segment")
        if parts[0] not in self.allowed_prefixes:
            raise ValueError(
                f"unsupported object prefix {parts[0]!r}; accepted: {sorted(self.allowed_prefixes)}"
            )
        object_name = _ascii_safe_object_key(object_name)
        try:
            self._ensure_bucket()
            extra: dict[str, Any] = {"ContentType": content_type}
            if metadata:
                # boto3 expects Metadata values as strings without the x-amz-meta- prefix.
                # Values must be ASCII; non-ASCII (e.g. Unicode filenames) are percent-encoded.
                extra["Metadata"] = _ascii_safe_metadata({str(k): str(v) for k, v in metadata.items()})
            self._client.upload_file(
                local_path,
                self.bucket_name,
                object_name,
                ExtraArgs=extra,
            )
        except ClientError as exc:
            raise ObjectStorageError(f"failed to upload object {object_name!r}") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError(f"failed to upload object {object_name!r}") from exc

        size_bytes = os.path.getsize(local_path)
        return StoredObject(
            bucket_name=self.bucket_name,
            object_name=object_name,
            storage_path=f"{self.bucket_name}/{object_name}",
            content_type=content_type,
            size_bytes=size_bytes,
        )

    def _presigned_get_url_sync(
        self,
        object_name: str,
        expires_seconds: int,
        disposition: ContentDisposition,
        download_filename: str | None,
    ) -> PresignedObjectUrl:
        normalised = self.object_name_from_reference(object_name)
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=normalised)
            content_type = content_type_for(normalised)
            if disposition == "auto":
                inline = _inline_default_for_content_type(content_type)
            else:
                inline = disposition == "inline"
            disp_header = _content_disposition_for(
                normalised,
                inline=inline,
                download_filename=download_filename,
            )
            if self._gcp_signer is not None:
                url = self._gcp_signer.signed_get_url(
                    endpoint_url=self._data_endpoint or _GCS_DEFAULT_ENDPOINT,
                    bucket=self.bucket_name,
                    key=normalised,
                    expires_seconds=expires_seconds,
                    query={
                        "response-content-type": content_type,
                        "response-content-disposition": disp_header,
                    },
                )
            else:
                url = self._presign_client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": normalised,
                        "ResponseContentType": content_type,
                        "ResponseContentDisposition": disp_header,
                    },
                    ExpiresIn=expires_seconds,
                )
            return PresignedObjectUrl(
                url=url,
                bucket_name=self.bucket_name,
                object_name=normalised,
                expires_seconds=expires_seconds,
            )
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError(f"object {normalised!r} was not found") from exc
            raise ObjectStorageError(f"failed to generate presigned URL for {normalised!r}") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError(f"failed to generate presigned URL for {normalised!r}") from exc
        except (OSError, KeyError, ValueError) as exc:
            # Metadata server or IAM signBlob failed (e.g. missing Token Creator role).
            if self._auth != "gcp":
                raise
            logger.warning("service-account URL signing failed for %r: %s", normalised, exc)
            raise ObjectStorageError(f"failed to generate presigned URL for {normalised!r}") from exc

    def _check_readiness_sync(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket_name)
            return
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"404", "NoSuchBucket", "NotFound", "404 Not Found"}:
                raise ObjectStorageError(
                    f"object storage readiness check failed for bucket {self.bucket_name!r}"
                ) from exc
        except BotoCoreError as exc:
            raise ObjectStorageError(
                f"object storage readiness check failed for bucket {self.bucket_name!r}"
            ) from exc

        if not self._auto_create_bucket:
            raise ObjectStorageError(
                f"object storage bucket {self.bucket_name!r} does not exist and "
                "auto_create_bucket is false; create the bucket in infra or enable auto-create in dev."
            )

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self._client.head_bucket(Bucket=self.bucket_name)
            self._bucket_ready = True
            return
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"404", "NoSuchBucket", "NotFound", "404 Not Found"}:
                raise ObjectStorageError(f"failed to check bucket {self.bucket_name!r}") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError(f"failed to check bucket {self.bucket_name!r}") from exc

        if not self._auto_create_bucket:
            raise ObjectStorageError(
                f"object storage bucket {self.bucket_name!r} does not exist and "
                "auto_create_bucket is false; create the bucket in infra or enable auto-create in dev."
            )
        try:
            create_kwargs: dict[str, Any] = {"Bucket": self.bucket_name}
            # us-east-1 is the only region that must omit LocationConstraint.
            region = getattr(self._client.meta, "region_name", None) or "us-east-1"
            if region != "us-east-1":
                create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
            self._client.create_bucket(**create_kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                raise ObjectStorageError(f"failed to create bucket {self.bucket_name!r}") from exc
        self._bucket_ready = True
