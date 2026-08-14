"""Stage A video visual enrichment — sample frames, vision-extract, persist.

Soft-fail: any error leaves the transcript pages intact and never fails
Stage A. Gated by ``ingest_video_visual_extraction_enabled``.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from mc_foundation.objectstore import ObjectStore
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import Settings, get_settings
from platform_service.db.models.source_image import SourceImage
from platform_service.db.models.source_page import SourcePage
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.objectstore import create_object_store
from platform_service.services.source_image_persist_service import (
    figure_object_name,
    figure_storage_path,
)
from platform_service.workers.extractors.video_frame_sampler import (
    SampledFrame,
    TimeRange,
    append_visual_section,
    sample_video_frames,
)
from platform_service.workers.extractors.vision_extractor import (
    VisionExtractionError,
    VisionExtractor,
)

logger = logging.getLogger(__name__)

SampleFramesFn = Callable[..., list[SampledFrame]]


class VideoVisualEnrichmentService:
    """Best-effort frame → vision → markdown + ``source_image`` for video."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        vision: VisionExtractor,
        settings: Settings | None = None,
        storage: ObjectStore | None = None,
        sample_frames_fn: SampleFramesFn | None = None,
    ) -> None:
        self._session = session
        self._vision = vision
        self._settings = settings or get_settings()
        self._storage = storage or create_object_store(settings=self._settings)
        self._repo = SourceRepository(session)
        self._sample_frames = sample_frames_fn or sample_video_frames

    async def enrich(
        self,
        *,
        source_document_id: UUID,
        source_path: str | Path,
        pages: list[SourcePage],
        empty_audio_fallback: bool = False,
    ) -> int:
        """Append visual markdown and persist frames. Returns frames persisted."""
        if not self._settings.ingest_video_visual_extraction_enabled and not empty_audio_fallback:
            return 0

        ranges = [
            TimeRange(start_ms=p.start_ms, end_ms=p.end_ms)
            for p in pages
            if p.start_ms is not None and p.end_ms is not None
        ]
        if not ranges:
            logger.info(
                "video visual enrichment skipped source_document_id=%s (no page timecodes)",
                source_document_id,
            )
            return 0

        try:
            frames = self._sample_frames(
                source_path,
                ranges,
                interval_ms=self._settings.ingest_video_frame_interval_ms,
                max_frames=self._settings.ingest_video_max_frames_per_document,
            )
        except Exception:
            logger.exception(
                "video frame sampling failed source_document_id=%s; continuing without visuals",
                source_document_id,
            )
            return 0

        if not frames:
            return 0

        pages_by_time = [p for p in pages if p.start_ms is not None and p.end_ms is not None]
        pages_by_time.sort(key=lambda p: (p.start_ms or 0, p.page_number))

        image_order_by_page: dict[int, int] = {}
        frames_persisted = 0
        for frame in frames:
            page = _page_for_timestamp(pages_by_time, frame.start_ms)
            if page is None:
                continue
            try:
                vision_md = await self._vision_markdown(frame)
            except Exception:
                logger.warning(
                    "video vision failed source_document_id=%s start_ms=%d; skipping frame",
                    source_document_id,
                    frame.start_ms,
                    exc_info=True,
                )
                continue
            if not vision_md.strip():
                continue

            order = image_order_by_page.get(page.page_number, 0)
            row = await self._persist_frame(
                source_document_id=source_document_id,
                page=page,
                frame=frame,
                image_order=order,
                vision_markdown=vision_md,
            )
            if row is None:
                continue
            image_order_by_page[page.page_number] = order + 1

            page.markdown_content = append_visual_section(
                page.markdown_content or "",
                start_ms=frame.start_ms,
                vision_markdown=vision_md,
            )
            frames_persisted += 1

        if frames_persisted:
            await self._session.flush()
            logger.info(
                "video visual enrichment source_document_id=%s frames=%d",
                source_document_id,
                frames_persisted,
            )
        return frames_persisted

    async def _vision_markdown(self, frame: SampledFrame) -> str:
        try:
            result = await self._vision.extract_page(
                page_image_bytes=frame.png_bytes,
                mime_type="image/png",
                page_label=f"video_frame_t={frame.start_ms}",
            )
        except VisionExtractionError:
            raise
        return result.markdown or ""

    async def _persist_frame(
        self,
        *,
        source_document_id: UUID,
        page: SourcePage,
        frame: SampledFrame,
        image_order: int,
        vision_markdown: str,
    ) -> SourceImage | None:
        object_name = figure_object_name(source_document_id, frame.content_sha256, suffix="png")
        storage_path = figure_storage_path(
            self._settings,
            source_document_id,
            frame.content_sha256,
            suffix="png",
        )
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(frame.png_bytes)
            await self._storage.put_object_from_local_file(
                object_name=object_name,
                local_path=tmp_path,
                content_type="image/png",
            )
        except Exception:
            logger.exception(
                "video frame upload failed source_document_id=%s sha=%s",
                source_document_id,
                frame.content_sha256,
            )
            return None
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

        excerpt = vision_markdown.strip()
        if len(excerpt) > 500:
            excerpt = excerpt[:497] + "..."
        row = SourceImage(
            source_document_id=source_document_id,
            source_page_id=page.id,
            page_number=page.page_number,
            image_order=image_order,
            storage_path=storage_path,
            content_type="image/png",
            content_sha256=frame.content_sha256,
            width_px=None,
            height_px=None,
            size_bytes=len(frame.png_bytes),
            alt_text=excerpt.split("\n", 1)[0][:200] if excerpt else None,
            nearby_text=excerpt or None,
            bbox_jsonb={"kind": "video_frame"},
            start_ms=frame.start_ms,
            end_ms=frame.end_ms,
        )
        self._session.add(row)
        return row


def _page_for_timestamp(pages: list[SourcePage], timestamp_ms: int) -> SourcePage | None:
    for page in pages:
        start = page.start_ms
        end = page.end_ms
        if start is None or end is None:
            continue
        if start <= timestamp_ms < end:
            return page
        # Last chunk may be inclusive of end when sample lands exactly on boundary.
        if timestamp_ms == end and page is pages[-1]:
            return page
    # Fallback: nearest page by start_ms.
    if not pages:
        return None
    return min(pages, key=lambda p: abs((p.start_ms or 0) - timestamp_ms))


__all__ = ["VideoVisualEnrichmentService"]
