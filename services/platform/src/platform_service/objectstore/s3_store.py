"""AWS S3."""

from __future__ import annotations

from platform_service.objectstore.boto_store import BotoLinkSigner, BotoObjectStore, clients_for
from platform_service.objectstore.config import StorageConfig


class S3ObjectStore(BotoObjectStore):
    """A key pair when configured; otherwise the AWS credential chain (instance role, IRSA)."""

    def __init__(self, config: StorageConfig) -> None:
        client, link = clients_for(config)
        super().__init__(config, client=client, link_signer=BotoLinkSigner(link, config.auth_description))
