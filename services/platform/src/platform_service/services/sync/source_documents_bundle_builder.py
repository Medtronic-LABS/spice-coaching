"""Build source-documents sync bundles for device sync."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from mc_contracts.sync import (
    SourceDocumentsSyncBundle,
    SourceDocumentSyncDownloadPayload,
    SourceDocumentThumbnailPresignedUrlPayload,
)
from mc_foundation.objectstore import ObjectStore
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import Settings, get_settings
from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.repositories.document_assignment_repository import (
    DocumentAssignmentRepository,
)
from platform_service.db.repositories.module_repository import ModuleRepository
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.services.sync.presign_service import SyncPresignService
from platform_service.services.sync.storage_path import sync_object_name


class SourceDocumentsBundleBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._presign = SyncPresignService(session)

    async def build(
        self,
        *,
        since: datetime,
        storage: ObjectStore,
        tenant_id: int | None = None,
        user_id: int | None = None,
        settings: Settings | None = None,
    ) -> SourceDocumentsSyncBundle:
        """Return module-linked (since-filtered) and assigned (full snapshot) docs."""
        effective_tenant = tenant_id if tenant_id is not None else DEFAULT_TENANT_ID
        source_repo = SourceRepository(self._session)

        module_doc_ids = await self._module_linked_document_ids(tenant_id=tenant_id)
        module_docs = await source_repo.list_by_ids_updated_since(module_doc_ids, since=since, source_types=["pdf"])
        module_docs_by_id = {doc.id: doc for doc in module_docs}

        assigned_at_by_id: dict[UUID, datetime] = {}
        assigned_docs_by_id: dict[UUID, SourceDocument] = {}
        if user_id is not None:
            assignments = await DocumentAssignmentRepository(self._session).list_for_user(
                user_id,
                tenant_id=effective_tenant,
            )
            assigned_ids = [row.source_document_id for row in assignments]
            if assigned_ids:
                assigned_rows = await source_repo.list_source_documents_by_ids(assigned_ids)
                for doc in assigned_rows:
                    if doc.status == "retired":
                        continue
                    assigned_docs_by_id[doc.id] = doc
                for row in assignments:
                    if row.source_document_id in assigned_docs_by_id:
                        assigned_at_by_id[row.source_document_id] = row.assigned_at

        settings = settings or get_settings()
        bucket_name = settings.object_storage_bucket_name

        all_doc_ids = list({*module_docs_by_id.keys(), *assigned_docs_by_id.keys()})
        presigned_by_doc, expires_by_doc, thumb_by_id = await self._presign_maps(
            document_ids=all_doc_ids,
            storage=storage,
            settings=settings,
        )

        source_documents: list[SourceDocumentSyncDownloadPayload] = []
        for doc in sorted(module_docs_by_id.values(), key=lambda d: (d.updated_at, d.id)):
            payload = self._payload(
                doc,
                assigned_at=None,
                presigned_by_doc=presigned_by_doc,
                expires_by_doc=expires_by_doc,
                thumb_by_id=thumb_by_id,
                bucket_name=bucket_name,
            )
            if payload is not None:
                source_documents.append(payload)

        assigned_documents: list[SourceDocumentSyncDownloadPayload] = []
        for doc_id in sorted(
            assigned_docs_by_id.keys(),
            key=lambda did: (assigned_at_by_id[did], did),
        ):
            payload = self._payload(
                assigned_docs_by_id[doc_id],
                assigned_at=assigned_at_by_id[doc_id],
                presigned_by_doc=presigned_by_doc,
                expires_by_doc=expires_by_doc,
                thumb_by_id=thumb_by_id,
                bucket_name=bucket_name,
            )
            if payload is not None:
                assigned_documents.append(payload)

        return SourceDocumentsSyncBundle(
            source_documents=source_documents,
            assigned_documents=assigned_documents,
            server_time_utc=datetime.now(UTC).isoformat(),
        )

    async def _module_linked_document_ids(self, *, tenant_id: int | None) -> list[UUID]:
        modules = await ModuleRepository(self._session).list_published_modules(tenant_id=tenant_id)
        doc_ids: list[UUID] = []
        seen: set[UUID] = set()
        for module in modules:
            for doc_id in module.source_document_ids or []:
                if doc_id not in seen:
                    seen.add(doc_id)
                    doc_ids.append(doc_id)
        return doc_ids

    async def _presign_maps(
        self,
        *,
        document_ids: list[UUID],
        storage: ObjectStore,
        settings: Settings | None,
    ) -> tuple[
        dict[UUID, str | None],
        dict[UUID, int | None],
        dict[UUID, SourceDocumentThumbnailPresignedUrlPayload],
    ]:
        if not document_ids:
            return {}, {}, {}

        doc_presign = await self._presign.get_source_document_presigned_urls(
            source_document_ids=document_ids,
            storage=storage,
            settings=settings,
        )
        presigned_by_doc: dict[UUID, str | None] = {
            entry.source_document_id: entry.presigned_url for entry in doc_presign.urls
        }
        expires_by_doc: dict[UUID, int | None] = {
            entry.source_document_id: entry.expires_seconds for entry in doc_presign.urls
        }
        thumb_presign = await self._presign.get_source_document_thumbnail_presigned_urls(
            source_document_ids=document_ids,
            storage=storage,
            settings=settings,
        )
        thumb_by_id = {entry.source_document_id: entry for entry in thumb_presign.urls}
        return presigned_by_doc, expires_by_doc, thumb_by_id

    @staticmethod
    def _payload(
        doc: SourceDocument,
        *,
        assigned_at: datetime | None,
        presigned_by_doc: dict[UUID, str | None],
        expires_by_doc: dict[UUID, int | None],
        thumb_by_id: dict[UUID, SourceDocumentThumbnailPresignedUrlPayload],
        bucket_name: str,
    ) -> SourceDocumentSyncDownloadPayload | None:
        object_name = sync_object_name(doc.original_storage_path, bucket_name=bucket_name)
        if object_name is None:
            return None
        thumb = thumb_by_id.get(doc.id)
        thumb_object_name = sync_object_name(doc.thumbnail_storage_path, bucket_name=bucket_name)
        return SourceDocumentSyncDownloadPayload(
            source_document_id=doc.id,
            title=doc.title,
            description=doc.description,
            source_type=doc.source_type,
            original_filename=doc.original_filename,
            storage_path=object_name,
            thumbnail_storage_path=thumb_object_name,
            assigned_at=assigned_at,
            duration_ms=doc.duration_ms,
            presigned_url=presigned_by_doc.get(doc.id),
            presigned_expires_seconds=expires_by_doc.get(doc.id),
            thumbnail_presigned_url=thumb.presigned_url if thumb is not None else None,
            thumbnail_presigned_expires_seconds=thumb.expires_seconds if thumb is not None else None,
        )
