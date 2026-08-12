"""Persist Stage A embedded figures to object storage + ``source_image``."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from uuid import UUID

from mc_foundation.objectstore import ObjectStore
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import Settings, get_settings
from platform_service.db.models.source_image import SourceImage
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.objectstore import create_object_store
from platform_service.workers.extractors.embedded_image_extractor import (
    ExtractedEmbeddedImage,
    ImageFilterConfig,
    extension_for_content_type,
    extract_embedded_images,
)

logger = logging.getLogger(__name__)

_SUPPORTED_SOURCE_TYPES = frozenset({"pdf", "pptx", "docx"})


def figure_object_name(source_document_id: UUID, content_sha256: str, *, suffix: str) -> str:
    clean_suffix = suffix.lstrip(".").lower() or "png"
    return f"ingest/figures/{source_document_id}/{content_sha256}.{clean_suffix}"


def figure_storage_path(
    settings: Settings,
    source_document_id: UUID,
    content_sha256: str,
    *,
    suffix: str,
) -> str:
    return (
        f"{settings.object_storage_bucket_name}/"
        f"{figure_object_name(source_document_id, content_sha256, suffix=suffix)}"
    )


class SourceImagePersistService:
    """Best-effort extract → upload → insert ``source_image`` rows."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        storage: ObjectStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._storage = storage or create_object_store(settings=self._settings)
        self._repo = SourceRepository(session)

    async def extract_and_persist(
        self,
        *,
        source_document_id: UUID,
        source_path: str | Path,
        source_type: str,
    ) -> list[SourceImage]:
        if source_type not in _SUPPORTED_SOURCE_TYPES:
            return []
        if not self._settings.ingest_source_image_extraction_enabled:
            return []

        filter_config = ImageFilterConfig(
            min_edge_px=self._settings.ingest_source_image_min_edge_px,
            min_bytes=self._settings.ingest_source_image_min_bytes,
            max_aspect_ratio=self._settings.ingest_source_image_max_aspect_ratio,
            min_strip_edge_px=self._settings.ingest_source_image_min_strip_edge_px,
        )
        try:
            extracted = extract_embedded_images(
                source_path,
                source_type,
                filter_config=filter_config,
            )
        except Exception:
            logger.exception(
                "embedded image extract failed source_document_id=%s source_type=%s",
                source_document_id,
                source_type,
            )
            return []

        if not extracted:
            return []

        pages = await self._repo.list_pages_for_document(source_document_id)
        page_id_by_number = {p.page_number: p.id for p in pages}

        persisted: list[SourceImage] = []
        for image in extracted:
            row = await self._persist_one(
                source_document_id=source_document_id,
                image=image,
                source_page_id=page_id_by_number.get(image.page_number),
            )
            if row is not None:
                persisted.append(row)

        if persisted:
            await self._session.flush()
            logger.info(
                "source_image persisted source_document_id=%s count=%d",
                source_document_id,
                len(persisted),
            )
        return persisted

    async def _persist_one(
        self,
        *,
        source_document_id: UUID,
        image: ExtractedEmbeddedImage,
        source_page_id: UUID | None,
    ) -> SourceImage | None:
        suffix = extension_for_content_type(image.content_type)
        if suffix is None:
            return None
        object_name = figure_object_name(source_document_id, image.content_sha256, suffix=suffix)
        storage_path = figure_storage_path(
            self._settings,
            source_document_id,
            image.content_sha256,
            suffix=suffix,
        )
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(image.data)
            await self._storage.put_object_from_local_file(
                object_name=object_name,
                local_path=tmp_path,
                content_type=image.content_type,
            )
        except Exception:
            logger.exception(
                "source_image upload failed source_document_id=%s sha=%s",
                source_document_id,
                image.content_sha256,
            )
            return None
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

        row = SourceImage(
            source_document_id=source_document_id,
            source_page_id=source_page_id,
            page_number=image.page_number,
            image_order=image.image_order,
            storage_path=storage_path,
            content_type=image.content_type,
            content_sha256=image.content_sha256,
            width_px=image.width_px,
            height_px=image.height_px,
            size_bytes=image.size_bytes,
            alt_text=image.alt_text,
            nearby_text=image.nearby_text,
            bbox_jsonb=image.bbox_jsonb,
        )
        self._session.add(row)
        return row


__all__ = [
    "SourceImagePersistService",
    "figure_object_name",
    "figure_storage_path",
]
