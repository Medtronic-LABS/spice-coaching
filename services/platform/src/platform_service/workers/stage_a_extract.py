"""Stage 1 — fused extraction + outline (was Stage A + Stage B).

Per `docs/ARCHITECTURE_RESET.md`. The flow per source document:

1. Count pages (page_renderer.count_pages).
2. Calibrate (sampled per-page text extraction → text_only / all_vision /
   per_page decision).
3. Extract every page (text or vision per the calibration), persisting
   SourcePage rows with markdown_content + extraction_method.
4. **Assemble the outline deterministically** from the per-page markdown
   (heading lines parsed by `markdown_outline_parser`). Persist
   `source_document.outline_jsonb`.
5. Stage 1 success contract: usable body/transcript text above
   `extraction_quality_text_empty_min_chars` (sum of stripped page markdown).
   Zero-page docs and empty/near-empty transcripts fail hard via
   `Stage1DocumentEmptyError`. Empty outline alone is non-fatal — the
   identifier can still run on body content. The orchestrator propagates
   Stage 1 failures as real ingestion_run_step failures so downstream
   stages never run on empty sources.

For video sources, after transcript pages are persisted, an optional flagged
visual enrichment path samples frames, runs VisionExtractor, appends
``## Visual`` markdown onto chunk pages, and stores ``source_image`` rows
with timecodes (soft-fail; never blocks transcript Stage A). Empty-audio
videos soft-fail transcription into timed empty pages so this visual path
can still contribute usable body text; Stage 1 then fails only if combined
markdown stays below the emptiness threshold.

The caller (pipeline_orchestrator) is responsible for:
- Creating the source_document row before invoking us
- Wrapping us in an ingestion_run for failure tracking
- Running Stage 2 (identify+draft) and Stage 3 (publish) afterward
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from uuid import UUID

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import get_settings
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.workers.extractors.base import (
    SourceExtractor,
    UnsupportedSourceTypeError,
)
from platform_service.workers.extractors.calibration import CalibrationDecision
from platform_service.workers.extractors.document_extractor import DocumentSourceExtractor
from platform_service.workers.extractors.media_extractor import MediaSourceExtractor
from platform_service.workers.extractors.page_renderer import (
    UnsupportedRenderError,
    count_pages,
    render_page_to_png,
)
from platform_service.workers.extractors.stage_a_document_path import run_document_path
from platform_service.workers.extractors.stage_a_media_path import run_media_transcript_path
from platform_service.workers.extractors.stage_a_text_guard import total_stripped_text_chars
from platform_service.workers.extractors.text_extractor import TextExtractionError
from platform_service.workers.extractors.vision_extractor import VisionExtractor
from platform_service.workers.stage_a_types import (
    Stage1DocumentEmptyError,
    Stage1ExtractionError,
    Stage1RecoveryFailedError,
    StageAResult,
)

logger = logging.getLogger(__name__)


class StageAExtractor:
    """Stage A orchestrator. One instance per ingestion run; reusable across runs."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        vision_extractor: VisionExtractor | None = None,
        ai_client: AIRuntimeClient | None = None,
        page_renderer=None,
        text_extractor_fn=None,
        media_transcriber_fn=None,
        extractors: dict[str, SourceExtractor] | None = None,
    ) -> None:
        self._session = session
        self._repo = SourceRepository(session)
        self._vision = vision_extractor or VisionExtractor()
        self._render_page = page_renderer or render_page_to_png
        if extractors is None:
            doc_ext = DocumentSourceExtractor(extract_pages_fn=text_extractor_fn)
            media_ext = MediaSourceExtractor(ai_client=ai_client, transcribe_fn=media_transcriber_fn)
            extractors = {t: doc_ext for t in doc_ext.supported_types} | {
                t: media_ext for t in media_ext.supported_types
            }
        self._extractors = extractors

    async def run(
        self,
        *,
        source_document_id: UUID,
        source_path: str | Path,
        source_type: str,
        primary_language: str | None = None,
    ) -> StageAResult:
        """Execute Stage A end-to-end for one source document."""
        resolved_primary_language = primary_language or get_settings().deployment_primary_locale
        reused = await self._try_reuse_existing_extraction(source_document_id)
        if reused is not None:
            return reused
        total_pages = await self._count_pages_or_fail(source_document_id, source_path, source_type)
        if total_pages == 0:
            await self._repo.mark_source_document_ingest_failed(source_document_id)
            await self._session.commit()
            raise Stage1DocumentEmptyError()

        extraction = await self._extract_source_or_fail(
            source_document_id, source_path, source_type, resolved_primary_language
        )
        if not extraction.requires_calibration:
            return await run_media_transcript_path(
                self._repo,
                self._session,
                source_document_id=source_document_id,
                text_pages=extraction.pages,
                total_pages=len(extraction.pages),
                primary_language=resolved_primary_language,
                source_path=source_path,
                source_type=source_type,
                vision_extractor=self._vision,
            )
        return await run_document_path(
            self,
            source_document_id=source_document_id,
            source_path=source_path,
            source_type=source_type,
            primary_language=resolved_primary_language,
            text_pages=extraction.pages,
            total_pages=total_pages,
        )

    async def _try_reuse_existing_extraction(self, source_document_id: UUID) -> StageAResult | None:
        """Reuse Stage A artifacts on in-place reingest when pages already look complete.

        Same-row reingest keeps ``source_page`` / outline; re-running extract would
        collide with ``uq_source_page_doc_page``. Admin extract retry clears pages
        first, so this short-circuit does not apply there.
        """
        doc = await self._repo.get_source_document(source_document_id)
        if doc is None:
            return None
        pages = await self._repo.list_pages_for_document(source_document_id)
        if not pages:
            return None
        min_chars = get_settings().extraction_quality_text_empty_min_chars
        page_markdowns = [p.markdown_content or "" for p in pages]
        if total_stripped_text_chars(page_markdowns) < min_chars:
            return None

        method_counts: dict[str, int] = {}
        for page in pages:
            method = page.extraction_method or "text"
            method_counts[method] = method_counts.get(method, 0) + 1

        cal_raw = doc.extraction_calibration_jsonb or {}
        calibration = CalibrationDecision(
            path=str(cal_raw.get("path") or "text_only"),
            sample_pages_evaluated=list(cal_raw.get("sample_pages_evaluated") or []),
            sample_pass_count=int(cal_raw.get("sample_pass_count") or 0),
            sample_fail_count=int(cal_raw.get("sample_fail_count") or 0),
            sample_fail_rate=float(cal_raw.get("sample_fail_rate") or 0.0),
        )
        outline = doc.outline_jsonb or {}
        section_count = len(outline.get("sections") or []) if isinstance(outline, dict) else 0

        await self._repo.update_status(
            source_document_id,
            status="ingesting",
            calibration=doc.extraction_calibration_jsonb,
        )
        await self._session.commit()
        logger.info(
            "Stage A reusing existing extraction source_document_id=%s pages=%d sections=%d",
            source_document_id,
            len(pages),
            section_count,
        )
        return StageAResult(
            source_document_id=source_document_id,
            total_pages=len(pages),
            pages_persisted=len(pages),
            extraction_method_counts=method_counts,
            calibration=calibration,
            outline_section_count=section_count,
        )

    async def _count_pages_or_fail(
        self, source_document_id: UUID, source_path: str | Path, source_type: str
    ) -> int:
        try:
            return await anyio.to_thread.run_sync(lambda: count_pages(source_path, source_type))
        except (UnsupportedRenderError, FileNotFoundError, Exception) as exc:
            logger.exception(
                "Stage A page count failed source_document_id=%s path=%s",
                source_document_id,
                source_path,
            )
            await self._repo.mark_source_document_ingest_failed(source_document_id)
            raise TextExtractionError(f"Stage A: cannot count pages: {exc}") from exc

    async def _extract_source_or_fail(
        self,
        source_document_id: UUID,
        source_path: str | Path,
        source_type: str,
        primary_language: str,
    ):
        extractor = self._extractors.get(source_type)
        if extractor is None:
            await self._repo.mark_source_document_ingest_failed(source_document_id)
            raise UnsupportedSourceTypeError(
                f"no Stage A extractor registered for source_type={source_type!r}"
            )
        try:
            return await extractor.extract(
                source_path,
                source_type=source_type,
                primary_language=primary_language,
            )
        except TextExtractionError:
            await self._repo.mark_source_document_ingest_failed(source_document_id)
            raise


__all__ = [
    "StageAExtractor",
    "StageAResult",
    "Stage1DocumentEmptyError",
    "Stage1ExtractionError",
    "Stage1RecoveryFailedError",
]


_ = uuid
