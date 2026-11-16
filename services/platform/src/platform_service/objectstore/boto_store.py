"""Shared boto3 object store. Providers (MinIO, AWS S3, GCS) differ only in client and link signer."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, BinaryIO, Protocol

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
)

from platform_service.objectstore.config import DEFAULT_REGION, StorageConfig
from platform_service.objectstore.naming import (
    NOT_FOUND_CODES,
    ascii_safe_metadata,
    ascii_safe_object_basename,
    ascii_safe_object_key,
    content_disposition_for,
    inline_default_for_content_type,
)

logger = logging.getLogger(__name__)


class LinkSigner(Protocol):
    """Builds a time-limited download URL for one object."""

    description: str

    def sign_get(
        self, *, bucket: str, key: str, expires_seconds: int, content_type: str, disposition: str
    ) -> str: ...


class BotoLinkSigner:
    """Signs links with the client's own credentials (a key pair or the AWS credential chain)."""

    def __init__(self, client: BaseClient, description: str) -> None:
        self._client = client
        self.description = description

    def sign_get(
        self, *, bucket: str, key: str, expires_seconds: int, content_type: str, disposition: str
    ) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ResponseContentType": content_type,
                "ResponseContentDisposition": disposition,
            },
            ExpiresIn=expires_seconds,
        )


def build_boto_client(
    *,
    endpoint_url: str | None,
    region: str,
    access_key: str = "",
    secret_key: str = "",
    path_style: bool = False,
    unsigned: bool = False,
) -> BaseClient:
    """A boto3 S3 client.

    - SigV4 always (AWS rejects SigV2); ``unsigned`` skips signing for callers that authenticate
      with a bearer token instead.
    - Checksums only when an API requires them: boto3 1.36+ otherwise sends uploads as aws-chunked
      with a CRC32 trailer, and GCS and older MinIO store that framing inside the object.
    - Empty keys leave credential discovery to boto3 (environment, instance role, IRSA).
    """
    kwargs: dict[str, Any] = {
        "service_name": "s3",
        "region_name": region or None,
        "config": Config(
            signature_version=UNSIGNED if unsigned else "s3v4",
            s3={"addressing_style": "path"} if path_style else {},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client(**kwargs)


def _is_not_found(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code", "") in NOT_FOUND_CODES


class BotoObjectStore:
    """Async wrapper around a sync boto3 S3 client. Subclasses supply the client and link signer."""

    def __init__(
        self,
        config: StorageConfig,
        *,
        client: BaseClient,
        link_signer: LinkSigner,
        create_bucket: bool = False,
    ) -> None:
        self.config = config
        self.bucket_name = config.bucket
        self.allowed_prefixes = config.allowed_prefixes or frozenset({"uploads"})
        self._client = client
        self._link_signer = link_signer
        self._create_bucket = create_bucket
        self._bucket_ready = False

    def describe(self) -> str:
        """One line for the start-up log; contains no credential."""
        return f"{self.config.describe()} links={self._link_signer.description}"

    def close(self) -> None:
        """Drop client references so connection pools can be reclaimed."""
        self._link_signer = None  # type: ignore[assignment]
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
        return await anyio.to_thread.run_sync(self._upload_file_sync, file_obj, filename, prefix, max_bytes)

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
        safe_filename = ascii_safe_object_basename(filename)
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
        except (ClientError, BotoCoreError) as exc:
            raise ObjectStorageError(f"failed to upload object {object_name!r}") from exc

        return self._stored(object_name, resolved_content_type, size_bytes)

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
        object_name = ascii_safe_object_key(object_name)
        try:
            self._ensure_bucket()
            extra: dict[str, Any] = {"ContentType": content_type}
            if metadata:
                # boto3 expects Metadata values as strings without the x-amz-meta- prefix.
                # Values must be ASCII; non-ASCII (e.g. Unicode filenames) are percent-encoded.
                extra["Metadata"] = ascii_safe_metadata({str(k): str(v) for k, v in metadata.items()})
            self._client.upload_file(local_path, self.bucket_name, object_name, ExtraArgs=extra)
        except (ClientError, BotoCoreError) as exc:
            raise ObjectStorageError(f"failed to upload object {object_name!r}") from exc

        return self._stored(object_name, content_type, os.path.getsize(local_path))

    def _stored(self, object_name: str, content_type: str, size_bytes: int) -> StoredObject:
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
        content_type = content_type_for(normalised)
        inline = (
            inline_default_for_content_type(content_type)
            if disposition == "auto"
            else disposition == "inline"
        )
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=normalised)
            url = self._link_signer.sign_get(
                bucket=self.bucket_name,
                key=normalised,
                expires_seconds=expires_seconds,
                content_type=content_type,
                disposition=content_disposition_for(
                    normalised, inline=inline, download_filename=download_filename
                ),
            )
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError(f"object {normalised!r} was not found") from exc
            raise ObjectStorageError(f"failed to generate presigned URL for {normalised!r}") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError(f"failed to generate presigned URL for {normalised!r}") from exc
        return PresignedObjectUrl(
            url=url,
            bucket_name=self.bucket_name,
            object_name=normalised,
            expires_seconds=expires_seconds,
        )

    def _bucket_exists(self, failure: str) -> bool:
        """True when the bucket is reachable, False when it is missing; any other error raises."""
        try:
            self._client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError as exc:
            if not _is_not_found(exc):
                raise ObjectStorageError(f"{failure} {self.bucket_name!r}") from exc
            return False
        except BotoCoreError as exc:
            raise ObjectStorageError(f"{failure} {self.bucket_name!r}") from exc

    def _missing_bucket_error(self) -> ObjectStorageError:
        return ObjectStorageError(
            f"object storage bucket {self.bucket_name!r} does not exist; create it in infrastructure "
            "(only a local MinIO may create its own bucket)"
        )

    def _check_readiness_sync(self) -> None:
        if self._bucket_exists("object storage readiness check failed for bucket"):
            return
        if not self._create_bucket:
            raise self._missing_bucket_error()

    def _ensure_bucket(self) -> None:
        """Create the bucket on first write, for stores allowed to. Cloud stores never look."""
        if not self._create_bucket or self._bucket_ready:
            return
        if not self._bucket_exists("failed to check bucket"):
            try:
                create_kwargs: dict[str, Any] = {"Bucket": self.bucket_name}
                # us-east-1 is the only region that must omit LocationConstraint.
                region = getattr(self._client.meta, "region_name", None) or DEFAULT_REGION
                if region != DEFAULT_REGION:
                    create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
                self._client.create_bucket(**create_kwargs)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                    raise ObjectStorageError(f"failed to create bucket {self.bucket_name!r}") from exc
        self._bucket_ready = True


def clients_for(
    config: StorageConfig, *, region: str | None = None, path_style: bool = False
) -> tuple[BaseClient, BaseClient]:
    """The (data, link) clients for a store that authenticates with the configured credentials.

    The link client is bound to the public endpoint when one is configured; otherwise it is the
    data client.
    """
    options: dict[str, Any] = {
        "region": region or config.region,
        "access_key": config.access_key,
        "secret_key": config.secret_key,
        "path_style": path_style,
    }
    data = build_boto_client(endpoint_url=config.endpoint, **options)
    if not config.public_endpoint:
        return data, data
    return data, build_boto_client(endpoint_url=config.public_endpoint, **options)
