"""MinIO (local development and self-hosted S3-compatible storage)."""

from __future__ import annotations

from platform_service.objectstore.boto_store import BotoLinkSigner, BotoObjectStore, clients_for
from platform_service.objectstore.config import StorageConfig


class MinioObjectStore(BotoObjectStore):
    """Key-pair auth, path-style URLs; the only store that may create its own bucket."""

    def __init__(self, config: StorageConfig) -> None:
        client, link = clients_for(config, path_style=True)
        super().__init__(
            config,
            client=client,
            link_signer=BotoLinkSigner(link, "access key"),
            create_bucket=config.create_bucket,
        )
