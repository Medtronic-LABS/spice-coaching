"""Persist Stage A embedded figures to object storage + ``source_image``."""

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
from platform_service.services.image_alt_text import clip_image_alt_text, is_usable_image_alt
from platform_service.workers.extractors.embedded_image_extractor import (
    ExtractedEmbeddedImage,
    ImageFilterConfig,
    extension_for_content_type,
    extract_embedded_images,
)
from platform_service.workers.extractors.vision_extractor import VisionExtractor

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
        vision: VisionExtractor | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._storage = storage or create_object_store(settings=self._settings)
        self._repo = SourceRepository(session)
        self._vision = vision

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
        alt_counts: dict[str, int] = {}
        for image in extracted:
            row = await self._persist_one(
                source_document_id=source_document_id,
                image=image,
                source_page_id=page_id_by_number.get(image.page_number),
                alt_counts=alt_counts,
            )
            if row is not None:
                persisted.append(row)

        if persisted:
            await self._session.flush()
            logger.info(
                "source_image persisted source_document_id=%s count=%d alt=%s",
                source_document_id,
                len(persisted),
                alt_counts,
            )
        return persisted

    async def _resolve_alt_text(
        self,
        image: ExtractedEmbeddedImage,
        *,
        alt_counts: dict[str, int],
    ) -> str | None:
        if is_usable_image_alt(image.alt_text):
            alt_counts["alt_document"] = alt_counts.get("alt_document", 0) + 1
            return clip_image_alt_text(image.alt_text)

        cached = await self._repo.find_usable_alt_text_by_sha256(image.content_sha256)
        if cached is not None:
            alt_counts["alt_sha256_reuse"] = alt_counts.get("alt_sha256_reuse", 0) + 1
            return clip_image_alt_text(cached)

        if not self._settings.ingest_source_image_llm_text_enabled:
            alt_counts["alt_skipped_flag"] = alt_counts.get("alt_skipped_flag", 0) + 1
            return None
        if self._vision is None:
            alt_counts["alt_llm_failed"] = alt_counts.get("alt_llm_failed", 0) + 1
            return None

        try:
            generated = await self._vision.extract_image_text(
                image_bytes=image.data,
                mime_type=image.content_type,
                label=image.content_sha256[:12],
            )
        except Exception:
            logger.exception(
                "source_image llm alt failed sha=%s",
                image.content_sha256,
            )
            alt_counts["alt_llm_failed"] = alt_counts.get("alt_llm_failed", 0) + 1
            return None

        clipped = clip_image_alt_text(generated)
        if clipped is None:
            alt_counts["alt_llm_failed"] = alt_counts.get("alt_llm_failed", 0) + 1
            return None
        alt_counts["alt_llm"] = alt_counts.get("alt_llm", 0) + 1
        return clipped

    async def _persist_one(
        self,
        *,
        source_document_id: UUID,
        image: ExtractedEmbeddedImage,
        source_page_id: UUID | None,
        alt_counts: dict[str, int],
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

        alt_text = await self._resolve_alt_text(image, alt_counts=alt_counts)
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
            alt_text=alt_text,
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
