"""Build the combined SourceDocumentsSyncBundle consumed by GET /sync/source-documents.

The Android SDK calls this single endpoint to populate both:
  - The Knowledge grid  (source_documents — all sync_published_visible docs)
  - The Training sub-tab (assigned_documents — audio/video assigned to the CHW)

Presigned URLs are generated inline so the device can download without a second
round-trip. Both lists carry the same SourceDocumentDownloadItem shape; the SDK
determines which list an item belongs to from assigned_at / source_type.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from mc_contracts.sync import SourceDocumentDownloadItem, SourceDocumentsSyncBundle
from mc_foundation.objectstore import ObjectStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import Settings, get_settings
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.services.source_thumbnail_service import presign_thumbnail
from platform_service.services.sync.presign_service import SyncPresignService
from platform_service.services.sync.video_assignment_resolver import resolve_assigned_videos


class SourceDocumentsBundleBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._presign = SyncPresignService(session)

    async def build(
        self,
        *,
        storage: ObjectStore,
        user_id: int | None = None,
        organization_ids: list[int] | None = None,
        settings: Settings | None = None,
    ) -> SourceDocumentsSyncBundle:
        settings = settings or get_settings()
        now_sec = int(datetime.now(UTC).timestamp())

        source_documents = await self._build_published(storage=storage, settings=settings, now_sec=now_sec)
        assigned_documents = (
            await self._build_assigned(
                user_id=user_id,
                organization_ids=organization_ids,
                storage=storage,
                settings=settings,
                now_sec=now_sec,
            )
            if user_id is not None
            else []
        )

        return SourceDocumentsSyncBundle(
            source_documents=source_documents,
            assigned_documents=assigned_documents,
            server_time_utc=datetime.now(UTC).isoformat(),
        )

    async def _build_published(
        self,
        *,
        storage: ObjectStore,
        settings: Settings,
        now_sec: int,
    ) -> list[SourceDocumentDownloadItem]:
        docs = await SourceRepository(self._session).list_sync_published_visible_documents(limit=200)
        if not docs:
            return []

        doc_ids = [doc.id for doc in docs]
        doc_by_id = {doc.id: doc for doc in docs}

        presign_resp = await self._presign.get_source_document_presigned_urls(
            source_document_ids=doc_ids,
            storage=storage,
            settings=settings,
        )
        url_by_id: dict[UUID, str | None] = {e.source_document_id: e.presigned_url for e in presign_resp.urls}
        expires_by_id: dict[UUID, int | None] = {e.source_document_id: e.expires_seconds for e in presign_resp.urls}

        thumb_resp = await self._presign.get_source_document_thumbnail_presigned_urls(
            source_document_ids=doc_ids,
            storage=storage,
            settings=settings,
        )
        thumb_url_by_id: dict[UUID, str | None] = {e.source_document_id: e.presigned_url for e in thumb_resp.urls}
        thumb_exp_by_id: dict[UUID, int | None] = {e.source_document_id: e.expires_seconds for e in thumb_resp.urls}

        return [
            SourceDocumentDownloadItem(
                source_document_id=doc_by_id[doc_id].id,
                source_type=doc_by_id[doc_id].source_type,
                title=doc_by_id[doc_id].title,
                original_filename=doc_by_id[doc_id].original_filename,
                assigned_at=None,
                presigned_url=url_by_id.get(doc_id),
                presigned_expires_seconds=expires_by_id.get(doc_id),
                thumbnail_presigned_url=thumb_url_by_id.get(doc_id),
                thumbnail_presigned_expires_seconds=thumb_exp_by_id.get(doc_id),
            )
            for doc_id in doc_ids
            if doc_id in doc_by_id
        ]

    async def _build_assigned(
        self,
        *,
        user_id: int,
        organization_ids: list[int] | None,
        storage: ObjectStore,
        settings: Settings,
        now_sec: int,
    ) -> list[SourceDocumentDownloadItem]:
        assigned = await resolve_assigned_videos(
            self._session,
            user_id=user_id,
            organization_ids=organization_ids,
        )
        if not assigned:
            return []

        video_ids = list(assigned.keys())
        stmt = select(SourceDocument).where(SourceDocument.id.in_(video_ids))
        docs = list((await self._session.execute(stmt)).scalars().all())
        if not docs:
            return []

        doc_by_id = {doc.id: doc for doc in docs}

        presign_resp = await self._presign.get_source_document_presigned_urls(
            source_document_ids=video_ids,
            storage=storage,
            settings=settings,
        )
        url_by_id: dict[UUID, str | None] = {e.source_document_id: e.presigned_url for e in presign_resp.urls}
        expires_by_id: dict[UUID, int | None] = {e.source_document_id: e.expires_seconds for e in presign_resp.urls}

        items: list[SourceDocumentDownloadItem] = []
        for video_id, assigned_at in sorted(assigned.items(), key=lambda kv: kv[1], reverse=True):
            doc = doc_by_id.get(video_id)
            if doc is None:
                continue
            thumb = await presign_thumbnail(storage, thumbnail_storage_path=doc.thumbnail_storage_path, settings=settings)
            items.append(
                SourceDocumentDownloadItem(
                    source_document_id=doc.id,
                    source_type=doc.source_type,
                    title=doc.title,
                    original_filename=doc.original_filename,
                    assigned_at=assigned_at,
                    presigned_url=url_by_id.get(video_id),
                    presigned_expires_seconds=expires_by_id.get(video_id),
                    thumbnail_presigned_url=thumb[0] if thumb else None,
                    thumbnail_presigned_expires_seconds=thumb[1] if thumb else None,
                )
            )
        return items
