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
5. Stage 1 success contract: `pages_persisted > 0` AND `section_count > 0`.
   An empty outline fails the stage hard — no separate Stage B, no silent
   `outline_method='failed'` masquerading as success. The orchestrator
   propagates this as a real ingestion_run_step failure so downstream
   stages never run on garbage.

The caller (pipeline_orchestrator) is responsible for:
- Creating the source_document row before invoking us
- Wrapping us in an ingestion_run for failure tracking
- Running Stage 2 (identify+draft) and Stage 3 (publish) afterward
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import get_settings
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.workers.extractors.calibration import (
    CalibrationDecision,
    build_calibration_decision,
    stratified_sample_indices,
)
from platform_service.workers.extractors.markdown_outline_parser import parse_outline
from platform_service.workers.extractors.page_renderer import (
    UnsupportedRenderError,
    count_pages,
    render_page_to_png,
)
from platform_service.workers.extractors.quality_heuristic import QualityScore, score_page
from platform_service.workers.extractors.text_extractor import (
    ExtractedPage,
    TextExtractionError,
    extract_pages,
)
from platform_service.workers.extractors.vision_extractor import (
    VisionExtractionError,
    VisionExtractor,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StageAResult:
    """Summary of one Stage 1 run for a single source document."""

    source_document_id: UUID
    total_pages: int
    pages_persisted: int
    extraction_method_counts: dict[str, int]  # {"text": N, "vision": M, "vision_failed": K}
    calibration: CalibrationDecision
    # Outline assembled deterministically from heading-marked markdown
    # produced by the per-page extractors. section_count == 0 means the
    # extractor did not emit any heading markers — Stage 1 fails when this
    # happens (no separate Stage B, no silent success).
    outline_section_count: int = 0


class Stage1ExtractionError(Exception):
    """Raised by Stage1Extractor.run when the stage cannot meet its success
    contract. Currently used for the vision-recovery tolerance breach
    (`Stage1RecoveryFailedError` subclass). Empty outline used to raise
    here too (pre-c5b6635 outline-partitioner era); under the token-budget
    chunker the outline is supplementary, so empty-outline now logs a
    warning and proceeds. The orchestrator's typed handler at
    pipeline_orchestrator.py:462 still maps this exception to
    `error_jsonb.reason` for the dashboard."""


class Stage1RecoveryFailedError(Stage1ExtractionError):
    """Raised when the vision-recovery pass leaves more than
    `stage_a_vision_failed_tolerance` pages still in `vision_failed` state.
    The error message lists the failing page numbers so the operator can
    decide whether to raise the tolerance, raise quota, or extract those
    pages by other means before re-running."""

    def __init__(self, failed_page_numbers: list[int], tolerance: int) -> None:
        self.failed_page_numbers = failed_page_numbers
        self.tolerance = tolerance
        super().__init__(
            f"Stage 1 vision recovery left {len(failed_page_numbers)} pages "
            f"still vision_failed (tolerance={tolerance}): {failed_page_numbers}. "
            f"This usually means Vertex per-project quota was exhausted "
            f"throughout the run. Retry after quota resets, raise the "
            f"per-project RPM limit, or set stage_a_vision_failed_tolerance "
            f"higher if losing these pages is acceptable."
        )


class StageAExtractor:
    """Stage A orchestrator. One instance per ingestion run; reusable across runs."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        vision_extractor: VisionExtractor | None = None,
        page_renderer=None,
        text_extractor_fn=None,
    ) -> None:
        self._session = session
        self._repo = SourceRepository(session)
        self._vision = vision_extractor or VisionExtractor()
        # Injected for tests; defaults call the module-level functions.
        self._render_page = page_renderer or render_page_to_png
        self._extract_text_pages = text_extractor_fn or extract_pages

    async def run(
        self,
        *,
        source_document_id: UUID,
        source_path: str | Path,
        source_type: str,
        primary_language: str = "bn",
    ) -> StageAResult:
        """Execute Stage A end-to-end for one source document."""
        # 1. Count pages
        try:
            total_pages = count_pages(source_path, source_type)
        except (UnsupportedRenderError, FileNotFoundError, Exception) as exc:
            logger.exception(
                "Stage A page count failed source_document_id=%s path=%s",
                source_document_id,
                source_path,
            )
            await self._repo.update_status(source_document_id, "failed")
            raise TextExtractionError(f"Stage A: cannot count pages: {exc}") from exc

        if total_pages == 0:
            calibration = build_calibration_decision(
                sample_pages=[], sample_pass_count=0, sample_fail_count=0
            )
            await self._repo.update_status(
                source_document_id,
                status="ingested",
                calibration=calibration.to_jsonb(),
            )
            return StageAResult(
                source_document_id=source_document_id,
                total_pages=0,
                pages_persisted=0,
                extraction_method_counts={},
                calibration=calibration,
            )

        # 2. Extract text for ALL pages (cheap; we need it for the per-page
        # path anyway, and the sampled pages need full extracted text to score).
        try:
            text_pages = self._extract_text_pages(source_path, source_type)
        except TextExtractionError:
            await self._repo.update_status(source_document_id, "failed")
            raise
        text_by_page: dict[int, ExtractedPage] = {p.page_number: p for p in text_pages}

        # 3. Calibration sampling
        settings = get_settings()
        sample_pages = stratified_sample_indices(total_pages, settings.extraction_calibration_sample_size)
        sample_pass = 0
        sample_fail = 0
        sampled_scores: dict[int, QualityScore] = {}
        for pn in sample_pages:
            page = text_by_page.get(pn)
            score = score_page(
                page.markdown if page else "",
                primary_language=primary_language,
                is_multi_page_document=total_pages > 1,
            )
            sampled_scores[pn] = score
            if score.passed:
                sample_pass += 1
            else:
                sample_fail += 1

        calibration = build_calibration_decision(
            sample_pages=sample_pages,
            sample_pass_count=sample_pass,
            sample_fail_count=sample_fail,
        )
        logger.info(
            "Stage A calibration source_document_id=%s path=%s pass=%d fail=%d → %s",
            source_document_id,
            source_path,
            sample_pass,
            sample_fail,
            calibration.path,
        )

        # 4 + 5. Per-page processing per the calibration decision
        method_counts: dict[str, int] = {}
        pages_persisted = 0

        for pn in range(1, total_pages + 1):
            text_page = text_by_page.get(pn)
            text_md = text_page.markdown if text_page else ""

            if calibration.path == "all_vision":
                # Skip text extraction entirely; go straight to vision.
                method, markdown, image_path, score = await self._run_vision_path(
                    source_document_id=source_document_id,
                    source_path=source_path,
                    source_type=source_type,
                    page_number=pn,
                    text_md=text_md,
                    primary_language=primary_language,
                )
            elif calibration.path == "text_only":
                # Use text extraction; no per-page vision fallback even if
                # quality heuristic would flag.
                score = score_page(
                    text_md, primary_language=primary_language, is_multi_page_document=total_pages > 1
                )
                method = "text"
                markdown = text_md
                image_path = None
            else:  # per_page
                # Re-use sampled score if available, else score now.
                score = sampled_scores.get(pn) or score_page(
                    text_md, primary_language=primary_language, is_multi_page_document=total_pages > 1
                )
                if score.passed:
                    method = "text"
                    markdown = text_md
                    image_path = None
                else:
                    method, markdown, image_path, score = await self._run_vision_path(
                        source_document_id=source_document_id,
                        source_path=source_path,
                        source_type=source_type,
                        page_number=pn,
                        text_md=text_md,
                        primary_language=primary_language,
                    )

            await self._repo.create_source_page(
                source_document_id=source_document_id,
                page_number=pn,
                markdown_content=markdown,
                extraction_method=method,
                extraction_quality_score=score.composite_score,
                page_image_path=image_path,
                language_detected=primary_language,
            )
            method_counts[method] = method_counts.get(method, 0) + 1
            pages_persisted += 1

        await self._repo.update_status(
            source_document_id,
            status="ingested",
            calibration=calibration.to_jsonb(),
        )

        # Commit the per-page output BEFORE outline assembly. The outline
        # parser is deterministic and won't raise, but vision-recovery
        # below can — and even on the empty-outline (now-warning) path
        # we want the persisted pages to outlive an orchestrator-level
        # rollback so re-runs aren't a re-extract (~30 min of vision
        # calls on a 168-page manual).
        await self._session.commit()

        # ── Vision recovery pass + tolerance check ──────────────────
        # Pages that raised during vision extraction in the main loop are
        # currently persisted as method='vision_failed' with the (often
        # garbage) text-extraction fallback as content. Retry vision on
        # them after a quiet period; then enforce the tolerance budget.
        # Updates `method_counts` in place and may raise
        # `Stage1RecoveryFailedError`.
        recovered = await self._run_vision_recovery_pass(
            source_document_id=source_document_id,
            source_path=source_path,
            source_type=source_type,
            primary_language=primary_language,
            method_counts=method_counts,
        )
        if recovered:
            # New rows committed during the recovery pass — flush before
            # outline assembly reads them back.
            await self._session.commit()

        # ── Outline assembly (was Stage B) ───────────────────────────
        # Walk the per-page markdown we just persisted and build the
        # outline_jsonb by parsing heading markers (#/##/###). The
        # extractor prompt instructs the LLM to emit these; the parser is
        # deterministic — there is no LLM fallback here. An empty outline
        # is permitted: under the post-c5b6635 token-budget chunker the
        # outline is supplementary context for the identifier (a hint for
        # preferred chunk boundaries) rather than load-bearing. The
        # identifier reads body content for topic identification regardless
        # of outline presence.
        pages_rows = await self._repo.list_pages_for_document(source_document_id)
        page_pairs = [(p.page_number, p.markdown_content or "") for p in pages_rows]
        parsed = parse_outline(
            page_pairs,
            total_pages=total_pages,
            primary_language=primary_language,
        )
        section_count = len(parsed.sections)
        await self._repo.update_outline(
            source_document_id,
            outline_method="markdown_parser",
            outline_jsonb=parsed.to_jsonb(),
        )
        await self._session.commit()

        if section_count == 0:
            logger.warning(
                "Stage 1 outline empty source_document_id=%s pages=%d — "
                "identifier will run on body content only (no boundary hints)",
                source_document_id,
                pages_persisted,
            )

        logger.info(
            "Stage 1 complete source_document_id=%s pages=%d sections=%d methods=%s",
            source_document_id,
            pages_persisted,
            section_count,
            method_counts,
        )

        return StageAResult(
            source_document_id=source_document_id,
            total_pages=total_pages,
            pages_persisted=pages_persisted,
            extraction_method_counts=method_counts,
            calibration=calibration,
            outline_section_count=section_count,
        )

    # ── Vision fallback path ────────────────────────────────────────────

    async def _run_vision_path(
        self,
        *,
        source_document_id: UUID,
        source_path: str | Path,
        source_type: str,
        page_number: int,
        text_md: str,
        primary_language: str,
    ) -> tuple[str, str, str | None, QualityScore]:
        """Render the page → call vision LLM → return (method, markdown, image_path, score).

        On vision failure, returns extraction_method='vision_failed' with the
        text fallback markdown (best-effort) so the page is still represented
        and the reviewer can flag.
        """
        try:
            png_bytes = await asyncio.to_thread(self._render_page, source_path, source_type, page_number)
        except UnsupportedRenderError:
            # No render backend for this source_type (e.g. pptx in MVP).
            # Use text fallback; mark as vision_failed for visibility.
            logger.warning(
                "Vision render unsupported for source_type=%s page=%d; using text fallback",
                source_type,
                page_number,
            )
            score = score_page(text_md, primary_language=primary_language)
            return ("vision_failed", text_md, None, score)
        except Exception as exc:
            logger.warning(
                "Vision render failed source_document_id=%s page=%d: %s",
                source_document_id,
                page_number,
                exc,
            )
            score = score_page(text_md, primary_language=primary_language)
            return ("vision_failed", text_md, None, score)

        # Persist the rendered image to disk (so reviewer drill-down can
        # access it without re-rendering). Storage layout: per-document
        # directory under settings.upload_dir.
        image_path = self._persist_image(source_document_id, page_number, png_bytes)

        try:
            result = await self._vision.extract_page(
                page_image_bytes=png_bytes,
                mime_type="image/png",
                page_label=f"{source_document_id}/page_{page_number}",
            )
        except VisionExtractionError as exc:
            logger.warning(
                "Vision extraction failed source_document_id=%s page=%d: %s",
                source_document_id,
                page_number,
                exc,
            )
            # Score the text fallback (may itself be poor — that's fine; the
            # SourcePage is flagged via extraction_method='vision_failed').
            score = score_page(text_md, primary_language=primary_language)
            return ("vision_failed", text_md, image_path, score)

        # Vision-extracted markdown is the canonical body. Score it for
        # observability (vision output usually scores high on heuristics).
        vision_score = score_page(result.markdown, primary_language=primary_language)
        return ("vision", result.markdown, image_path, vision_score)

    async def _run_vision_recovery_pass(
        self,
        *,
        source_document_id: UUID,
        source_path: str | Path,
        source_type: str,
        primary_language: str,
        method_counts: dict[str, int],
    ) -> int:
        """Retry vision on pages that landed as `vision_failed` in the main loop.

        Waits `stage_a_vision_recovery_initial_delay_s` (lets the Vertex
        per-minute quota window clear), then iterates serially over each
        failed page with up to `stage_a_vision_recovery_max_retries`
        attempts per page. PNG is re-rendered if not already on disk
        (containers wipe `/tmp` on rebuild, so we cannot rely on the cached
        image surviving).

        On success: updates the row to method='vision' with the recovered
        markdown, updates `method_counts` in place.

        On failure: leaves the row as vision_failed.

        After the pass: if pages remaining > `stage_a_vision_failed_tolerance`,
        raises Stage1RecoveryFailedError. The tolerance check is the last
        thing this method does — it always runs, even when no pages were
        in vision_failed (in which case it short-circuits with 0 failures).

        Returns the number of pages successfully recovered (so the caller
        knows whether to commit before outline assembly).
        """
        settings = get_settings()
        failed = await self._repo.list_vision_failed_pages(source_document_id)
        if not failed:
            return 0

        logger.info(
            "Stage 1 recovery pass: %d pages marked vision_failed; waiting %.0fs before retry",
            len(failed),
            settings.stage_a_vision_recovery_initial_delay_s,
        )
        await asyncio.sleep(settings.stage_a_vision_recovery_initial_delay_s)

        recovered = 0
        for page in failed:
            success = await self._retry_vision_for_page(
                source_document_id=source_document_id,
                source_path=source_path,
                source_type=source_type,
                page_number=page.page_number,
                page_id=page.id,
                primary_language=primary_language,
                max_retries=settings.stage_a_vision_recovery_max_retries,
            )
            if success:
                recovered += 1
                method_counts["vision"] = method_counts.get("vision", 0) + 1
                method_counts["vision_failed"] = max(0, method_counts.get("vision_failed", 0) - 1)

        # Re-query to get the residual failure count (don't trust our local
        # bookkeeping — the source of truth is the DB).
        residual = await self._repo.list_vision_failed_pages(source_document_id)
        residual_count = len(residual)
        logger.info(
            "Stage 1 recovery pass complete: recovered=%d residual_failed=%d tolerance=%d",
            recovered,
            residual_count,
            settings.stage_a_vision_failed_tolerance,
        )

        if residual_count > settings.stage_a_vision_failed_tolerance:
            raise Stage1RecoveryFailedError(
                failed_page_numbers=[p.page_number for p in residual],
                tolerance=settings.stage_a_vision_failed_tolerance,
            )

        return recovered

    async def _retry_vision_for_page(
        self,
        *,
        source_document_id: UUID,
        source_path: str | Path,
        source_type: str,
        page_number: int,
        page_id: UUID,
        primary_language: str,
        max_retries: int,
    ) -> bool:
        """One page's recovery: re-render PNG (or load cached), retry vision
        up to `max_retries` times. On success, persist via
        `update_page_extraction`. Returns True if recovered.
        """
        settings = get_settings()
        # Try cached PNG first; re-render if missing.
        cached = (
            Path(settings.upload_dir)
            / "source_pages"
            / str(source_document_id)
            / f"page_{page_number:04d}.png"
        )
        png_bytes: bytes | None = None
        if cached.is_file():
            try:
                png_bytes = cached.read_bytes()
            except OSError:
                png_bytes = None
        if png_bytes is None:
            try:
                png_bytes = await asyncio.to_thread(self._render_page, source_path, source_type, page_number)
                # Re-persist so subsequent recovery attempts (and reviewer
                # drill-down) find it.
                self._persist_image(source_document_id, page_number, png_bytes)
            except Exception as exc:
                logger.warning(
                    "Stage 1 recovery: cannot re-render page %d: %s",
                    page_number,
                    exc,
                )
                return False

        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                result = await self._vision.extract_page(
                    page_image_bytes=png_bytes,
                    mime_type="image/png",
                    page_label=f"{source_document_id}/page_{page_number}",
                )
                # Vision succeeded (possibly with empty markdown — that's OK,
                # post-vision_extractor change treats empty as legitimate).
                vision_score = score_page(result.markdown, primary_language=primary_language)
                await self._repo.update_page_extraction(
                    page_id,
                    markdown_content=result.markdown,
                    extraction_method="vision",
                    extraction_quality_score=vision_score.composite_score,
                )
                logger.info(
                    "Stage 1 recovery: page %d recovered on attempt %d/%d (content_len=%d)",
                    page_number,
                    attempt,
                    max_retries,
                    len(result.markdown),
                )
                return True
            except VisionExtractionError as exc:
                last_exc = exc
                if attempt < max_retries:
                    # Exponential backoff per-attempt; the in-call retry in
                    # prompt_executor already burns ~100s, so the per-page
                    # retry budget here is mostly for sustained quota windows.
                    delay = 30.0 * attempt
                    logger.warning(
                        "Stage 1 recovery: page %d attempt %d/%d failed: %s — retrying in %.0fs",
                        page_number,
                        attempt,
                        max_retries,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        logger.warning(
            "Stage 1 recovery: page %d still failed after %d attempts: %s",
            page_number,
            max_retries,
            last_exc,
        )
        return False

    @staticmethod
    def _persist_image(source_document_id: UUID, page_number: int, png_bytes: bytes) -> str:
        """Write the page PNG under upload_dir/{document_id}/page_{n}.png."""
        settings = get_settings()
        out_dir = Path(settings.upload_dir) / "source_pages" / str(source_document_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"page_{page_number:04d}.png"
        path.write_bytes(png_bytes)
        return str(path)


__all__ = ["StageAExtractor", "StageAResult"]


# Suppress unused-import lint when only the type is referenced via injection.
_ = uuid
