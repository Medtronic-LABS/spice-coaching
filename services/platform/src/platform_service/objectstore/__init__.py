"""Platform object-store adapters: MinIO, AWS S3 and Google Cloud Storage (see ``config.py``)."""

from platform_service.objectstore.factory import announce_object_store, create_object_store

__all__ = ["announce_object_store", "create_object_store"]
