"""Stage A audio/video transcript path — skips document calibration.

For ``source_type=video`` with visual extraction enabled, samples frames,
vision-extracts them, appends markdown onto transcript pages, and persists
``source_image`` rows (soft-fail). Empty-audio videos may arrive with timed
empty transcript pages; enrichment is still attempted so visuals can satisfy
the Stage 1 text guard.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.services.video_visual_enrichment import VideoVisualEnrichmentService
from platform_service.workers.extractors.calibration import CalibrationDecision
from platform_service.workers.extractors.extraction_markdown import persist_markdown_content
from platform_service.workers.extractors.stage_a_outline_assembler import assemble_outline_from_page_pairs
from platform_service.workers.extractors.stage_a_text_guard import assert_document_has_text
from platform_service.workers.extractors.text_extractor import ExtractedPage
from platform_service.workers.extractors.vision_extractor import VisionExtractor
from platform_service.workers.stage_a_types import StageAResult

logger = logging.getLogger(__name__)


async def run_media_transcript_path(
    repo: SourceRepository,
    session: AsyncSession,
    *,
    source_document_id: UUID,
    text_pages: list[ExtractedPage],
    total_pages: int,
    primary_language: str,
    source_path: str | Path | None = None,
    source_type: str | None = None,
    vision_extractor: VisionExtractor | None = None,
) -> StageAResult:
    """Persist transcript markdown directly, without document-text calibration."""
    calibration = CalibrationDecision(
        path="media_transcript",
        sample_pages_evaluated=[],
        sample_pass_count=0,
        sample_fail_count=0,
        sample_fail_rate=0.0,
    )
    method_counts = {"transcript": 0}
    pages_persisted = 0
    persisted_pages = []
    for page in text_pages:
        row = await repo.create_source_page(
            source_document_id=source_document_id,
            page_number=page.page_number,
            markdown_content=persist_markdown_content(page.markdown),
            extraction_method="transcript",
            extraction_quality_score=(
                page.extraction_quality_score if page.extraction_quality_score is not None else 0.85
            ),
            page_image_path=None,
            language_detected=page.language_detected or primary_language,
            start_ms=page.start_ms,
            end_ms=page.end_ms,
        )
        persisted_pages.append(row)
        method_counts["transcript"] += 1
        pages_persisted += 1

    empty_audio = all(not (page.markdown or "").strip() for page in text_pages)
    if source_type == "video" and source_path is not None and vision_extractor is not None:
        if empty_audio:
            logger.info(
                "Stage A video empty-audio fallback: proceeding with visual enrichment "
                "source_document_id=%s pages=%d",
                source_document_id,
                pages_persisted,
            )
        try:
            enricher = VideoVisualEnrichmentService(
                session,
                vision=vision_extractor,
            )
            frames = await enricher.enrich(
                source_document_id=source_document_id,
                source_path=source_path,
                pages=persisted_pages,
                empty_audio_fallback=empty_audio,
            )
            if frames:
                method_counts["video_visual"] = frames
        except Exception:
            logger.exception(
                "video visual enrichment failed source_document_id=%s; continuing with transcript",
                source_document_id,
            )

    await repo.update_status(
        source_document_id,
        status="ingesting",
        calibration=calibration.to_jsonb(),
    )

    page_pairs = [
        (p.page_number, persist_markdown_content(p.markdown_content or "")) for p in persisted_pages
    ]
    section_count = await assemble_outline_from_page_pairs(
        repo,
        session,
        source_document_id=source_document_id,
        page_pairs=page_pairs,
        total_pages=total_pages,
        primary_language=primary_language,
        empty_outline_log=(
            "Stage 1 media transcript produced no outline sections for source_document_id=%s; proceeding"
        ),
    )
    await assert_document_has_text(
        repo,
        session,
        source_document_id=source_document_id,
        page_markdowns=[md for _, md in page_pairs],
        total_pages=total_pages,
    )

    return StageAResult(
        source_document_id=source_document_id,
        total_pages=total_pages,
        pages_persisted=pages_persisted,
        extraction_method_counts=method_counts,
        calibration=calibration,
        outline_section_count=section_count,
    )
