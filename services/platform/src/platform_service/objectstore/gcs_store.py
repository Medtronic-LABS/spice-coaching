"""Google Cloud Storage, through its S3-compatible XML API."""

from __future__ import annotations

import logging

from mc_foundation.objectstore import ObjectStorageError

from platform_service.objectstore.boto_store import (
    BotoLinkSigner,
    BotoObjectStore,
    LinkSigner,
    build_boto_client,
    clients_for,
)
from platform_service.objectstore.config import StorageConfig
from platform_service.objectstore.gcp_identity import (
    GcpMetadataToken,
    GcpServiceAccountSigner,
    install_bearer_token,
)

logger = logging.getLogger(__name__)

# GCS ignores the S3 region; SigV4 still needs one in the credential scope.
_GCS_REGION = "auto"


class ServiceAccountLinkSigner:
    """Signs links as the service account attached to the workload (no stored key)."""

    description = "attached service account (IAM signBlob)"

    def __init__(self, signer: GcpServiceAccountSigner, endpoint_url: str) -> None:
        self._signer = signer
        self._endpoint_url = endpoint_url

    def sign_get(
        self, *, bucket: str, key: str, expires_seconds: int, content_type: str, disposition: str
    ) -> str:
        try:
            return self._signer.signed_get_url(
                endpoint_url=self._endpoint_url,
                bucket=bucket,
                key=key,
                expires_seconds=expires_seconds,
                query={"response-content-type": content_type, "response-content-disposition": disposition},
            )
        except (OSError, KeyError, ValueError) as exc:
            # Metadata server or IAM signBlob failed (e.g. missing Token Creator role).
            logger.warning("service-account URL signing failed: %s: %s", type(exc).__name__, exc)
            raise ObjectStorageError(f"failed to generate presigned URL for {key!r}") from exc


class GcsObjectStore(BotoObjectStore):
    """With an HMAC key pair: the key signs data calls and links.

    Without one: the workload's service account (GKE Workload Identity) authenticates data calls
    with a bearer token and signs links through IAM ``signBlob``.
    """

    def __init__(self, config: StorageConfig) -> None:
        if config.has_keys:
            client, link = clients_for(config, region=_GCS_REGION, path_style=True)
            signer: LinkSigner = BotoLinkSigner(link, "HMAC key")
        else:
            token = GcpMetadataToken()
            client = build_boto_client(
                endpoint_url=config.endpoint, region=_GCS_REGION, path_style=True, unsigned=True
            )
            install_bearer_token(client, token)
            signer = ServiceAccountLinkSigner(GcpServiceAccountSigner(token), config.endpoint or "")
        super().__init__(config, client=client, link_signer=signer)
