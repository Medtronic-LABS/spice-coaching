"""Batch presign helpers for device sync endpoints."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID

from mc_contracts.sync import (
    SourceDocumentPresignedUrlPayload,
    SourceDocumentsPresignResponse,
    SourceDocumentThumbnailPresignedUrlPayload,
    SourceDocumentThumbnailsPresignResponse,
    StoragePathPresignedUrlPayload,
    StoragePathsPresignResponse,
)
from mc_foundation.objectstore import (
    ObjectNotFoundError,
    ObjectStorageError,
    ObjectStore,
    looks_like_object_storage_storage_path,
)
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import Settings, get_settings
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.repositories.module_repository import ModuleRepository
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.services.source_thumbnail_service import presign_thumbnail
from platform_service.services.sync.storage_path import (
    is_batch_presign_object_name,
    sync_object_name,
)

logger = logging.getLogger(__name__)

PayloadT = TypeVar("PayloadT")


class SyncPresignService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_source_document_presigned_urls(
        self,
        *,
        source_document_ids: list[UUID],
        storage: ObjectStore,
        settings: Settings | None = None,
        tenant_id: int | None = None,
    ) -> SourceDocumentsPresignResponse:
        """Return presigned GET URLs for object-storage-backed source documents.

        Unknown ids, legacy filesystem paths, and presign failures are listed in
        ``missing_ids`` without failing the whole batch.
        """
        settings = settings or get_settings()
        ttl = settings.admin_file_presigned_max_seconds
        bucket_name = settings.object_storage_bucket_name

        if not source_document_ids:
            return SourceDocumentsPresignResponse(
                urls=[],
                missing_ids=[],
                server_time_utc=datetime.now(UTC).isoformat(),
            )

        module_repo = ModuleRepository(self._session)
        allowed_doc_ids: set[UUID] | None = None
        if tenant_id is not None:
            allowed_doc_ids = await module_repo.filter_source_document_ids_for_tenant(
                source_document_ids,
                tenant_id,
            )

        docs = await SourceRepository(self._session).list_source_documents_by_ids(source_document_ids)
        doc_by_id = {doc.id: doc for doc in docs}

        urls: list[SourceDocumentPresignedUrlPayload] = []
        missing_ids: list[UUID] = []

        for doc_id in source_document_ids:
            doc = doc_by_id.get(doc_id)
            if doc is None:
                missing_ids.append(doc_id)
                continue
            if allowed_doc_ids is not None and doc_id not in allowed_doc_ids:
                missing_ids.append(doc_id)
                continue

            storage_path = doc.original_storage_path
            if not looks_like_object_storage_storage_path(storage_path, bucket_name=bucket_name):
                logger.debug(
                    "Skipping presign for non-object-storage source_document %s path=%s",
                    doc.id,
                    storage_path,
                )
                missing_ids.append(doc_id)
                continue

            object_name = sync_object_name(storage_path, bucket_name=bucket_name)
            if object_name is None:
                missing_ids.append(doc_id)
                continue

            try:
                presigned = await storage.presigned_get_url(
                    object_name=storage_path,
                    expires_seconds=ttl,
                    download_filename=doc.original_filename,
                )
            except ObjectNotFoundError:
                logger.warning(
                    "Presign: object missing for source_document %s path=%s",
                    doc.id,
                    storage_path,
                )
                missing_ids.append(doc_id)
                continue
            except (ObjectStorageError, ValueError) as exc:
                logger.warning("Presign failed for source_document %s: %s", doc.id, exc)
                missing_ids.append(doc_id)
                continue

            urls.append(
                SourceDocumentPresignedUrlPayload(
                    source_document_id=doc.id,
                    storage_path=object_name,
                    presigned_url=presigned.url,
                    expires_seconds=ttl,
                )
            )

        return SourceDocumentsPresignResponse(
            urls=urls,
            missing_ids=missing_ids,
            server_time_utc=datetime.now(UTC).isoformat(),
        )

    async def get_source_document_thumbnail_presigned_urls(
        self,
        *,
        source_document_ids: list[UUID],
        storage: ObjectStore,
        settings: Settings | None = None,
        tenant_id: int | None = None,
    ) -> SourceDocumentThumbnailsPresignResponse:
        """Return presigned GET URLs for source document thumbnails (partial success)."""
        settings = settings or get_settings()

        if not source_document_ids:
            return SourceDocumentThumbnailsPresignResponse(
                urls=[],
                missing_ids=[],
                server_time_utc=datetime.now(UTC).isoformat(),
            )

        module_repo = ModuleRepository(self._session)
        allowed_doc_ids: set[UUID] | None = None
        if tenant_id is not None:
            allowed_doc_ids = await module_repo.filter_source_document_ids_for_tenant(
                source_document_ids,
                tenant_id,
            )

        docs = await SourceRepository(self._session).list_source_documents_by_ids(source_document_ids)
        doc_by_id = {doc.id: doc for doc in docs}
        if allowed_doc_ids is not None:
            doc_by_id = {doc_id: doc for doc_id, doc in doc_by_id.items() if doc_id in allowed_doc_ids}

        urls, missing_ids = await self._presign_thumbnail_batch(
            entity_ids=source_document_ids,
            entity_by_id=doc_by_id,
            get_storage_path=lambda doc: doc.thumbnail_storage_path,
            build_payload=lambda doc_id, storage_path, presigned_url, expires_seconds: (
                SourceDocumentThumbnailPresignedUrlPayload(
                    source_document_id=doc_id,
                    storage_path=storage_path,
                    presigned_url=presigned_url,
                    expires_seconds=expires_seconds,
                )
            ),
            storage=storage,
            settings=settings,
        )

        return SourceDocumentThumbnailsPresignResponse(
            urls=urls,
            missing_ids=missing_ids,
            server_time_utc=datetime.now(UTC).isoformat(),
        )

    async def get_presigned_urls_for_storage_paths(
        self,
        *,
        storage_paths: list[str],
        storage: ObjectStore,
        settings: Settings | None = None,
    ) -> StoragePathsPresignResponse:
        """Return presigned GET URLs for object names (partial success).

        Accepts object names only (same normalisation as ``GET /admin/files/presigned-url``).
        Full ``bucket/key`` refs and filesystem paths are listed in ``missing_paths``.
        Successful rows echo the client-supplied path.
        """
        settings = settings or get_settings()
        ttl = settings.admin_file_presigned_max_seconds
        bucket_name = settings.object_storage_bucket_name

        urls: list[StoragePathPresignedUrlPayload] = []
        missing_paths: list[str] = []

        for storage_path in storage_paths:
            if not is_batch_presign_object_name(storage_path, bucket_name=bucket_name):
                logger.debug(
                    "Skipping presign for non-object-name path=%s",
                    storage_path,
                )
                missing_paths.append(storage_path)
                continue

            try:
                presigned = await storage.presigned_get_url(
                    object_name=storage_path,
                    expires_seconds=ttl,
                    disposition="auto",
                )
            except ObjectNotFoundError:
                logger.warning("Presign: object missing for path=%s", storage_path)
                missing_paths.append(storage_path)
                continue
            except (ObjectStorageError, ValueError) as exc:
                logger.warning("Presign failed for path=%s: %s", storage_path, exc)
                missing_paths.append(storage_path)
                continue

            urls.append(
                StoragePathPresignedUrlPayload(
                    storage_path=storage_path,
                    presigned_url=presigned.url,
                    expires_seconds=ttl,
                )
            )

        return StoragePathsPresignResponse(
            urls=urls,
            missing_paths=missing_paths,
            server_time_utc=datetime.now(UTC).isoformat(),
        )

    async def _presign_thumbnail_batch(
        self,
        *,
        entity_ids: list[UUID],
        entity_by_id: dict[UUID, SourceDocument],
        get_storage_path: Callable[[SourceDocument], str | None],
        build_payload: Callable[[UUID, str, str, int], PayloadT],
        storage: ObjectStore,
        settings: Settings,
    ) -> tuple[list[PayloadT], list[UUID]]:
        urls: list[PayloadT] = []
        missing_ids: list[UUID] = []
        bucket_name = settings.object_storage_bucket_name

        for entity_id in entity_ids:
            entity = entity_by_id.get(entity_id)
            if entity is None:
                missing_ids.append(entity_id)
                continue

            storage_path = get_storage_path(entity)
            if not storage_path:
                missing_ids.append(entity_id)
                continue

            thumb_presign = await presign_thumbnail(
                storage,
                thumbnail_storage_path=storage_path,
                settings=settings,
            )
            if thumb_presign is None:
                missing_ids.append(entity_id)
                continue

            object_name = sync_object_name(storage_path, bucket_name=bucket_name)
            if object_name is None:
                missing_ids.append(entity_id)
                continue

            presigned_url, expires_seconds = thumb_presign
            urls.append(build_payload(entity_id, object_name, presigned_url, expires_seconds))

        return urls, missing_ids
