"""Unit tests for media Stage A path with optional video visual enrichment."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from platform_service.workers.extractors.stage_a_media_path import run_media_transcript_path
from platform_service.workers.extractors.text_extractor import ExtractedPage


@pytest.mark.asyncio
async def test_media_path_audio_skips_visual_enrichment() -> None:
    page_row = SimpleNamespace(
        id=uuid4(),
        page_number=1,
        start_ms=0,
        end_ms=30_000,
        markdown_content="# Transcript (chunk 1)\n\nhello world enough text here",
    )
    repo = AsyncMock()
    repo.create_source_page = AsyncMock(return_value=page_row)
    repo.update_status = AsyncMock()
    session = AsyncMock()
    vision = MagicMock()

    with (
        patch(
            "platform_service.workers.extractors.stage_a_media_path.assemble_outline_from_page_pairs",
            AsyncMock(return_value=0),
        ),
        patch(
            "platform_service.workers.extractors.stage_a_media_path.assert_document_has_text",
            AsyncMock(),
        ),
        patch(
            "platform_service.workers.extractors.stage_a_media_path.VideoVisualEnrichmentService",
        ) as EnrichCls,
    ):
        result = await run_media_transcript_path(
            repo,
            session,
            source_document_id=uuid4(),
            text_pages=[
                ExtractedPage(
                    page_number=1,
                    markdown="# Transcript (chunk 1)\n\nhello world enough text here",
                    start_ms=0,
                    end_ms=30_000,
                    extraction_quality_score=0.9,
                )
            ],
            total_pages=1,
            primary_language="bn",
            source_path="/tmp/a.mp3",
            source_type="audio",
            vision_extractor=vision,
        )

    EnrichCls.assert_not_called()
    assert result.extraction_method_counts == {"transcript": 1}


@pytest.mark.asyncio
async def test_media_path_video_invokes_enrichment() -> None:
    page_row = SimpleNamespace(
        id=uuid4(),
        page_number=1,
        start_ms=0,
        end_ms=60_000,
        markdown_content="# Transcript (chunk 1)\n\nhello world enough text here",
    )
    repo = AsyncMock()
    repo.create_source_page = AsyncMock(return_value=page_row)
    repo.update_status = AsyncMock()
    session = AsyncMock()
    vision = MagicMock()
    enrich_instance = AsyncMock()
    enrich_instance.enrich = AsyncMock(return_value=2)

    with (
        patch(
            "platform_service.workers.extractors.stage_a_media_path.assemble_outline_from_page_pairs",
            AsyncMock(return_value=1),
        ),
        patch(
            "platform_service.workers.extractors.stage_a_media_path.assert_document_has_text",
            AsyncMock(),
        ),
        patch(
            "platform_service.workers.extractors.stage_a_media_path.VideoVisualEnrichmentService",
            return_value=enrich_instance,
        ) as EnrichCls,
    ):
        result = await run_media_transcript_path(
            repo,
            session,
            source_document_id=uuid4(),
            text_pages=[
                ExtractedPage(
                    page_number=1,
                    markdown="# Transcript (chunk 1)\n\nhello world enough text here",
                    start_ms=0,
                    end_ms=60_000,
                    extraction_quality_score=0.9,
                )
            ],
            total_pages=1,
            primary_language="bn",
            source_path="/tmp/v.mp4",
            source_type="video",
            vision_extractor=vision,
        )

    EnrichCls.assert_called_once()
    enrich_instance.enrich.assert_awaited_once()
    assert result.extraction_method_counts["transcript"] == 1
    assert result.extraction_method_counts["video_visual"] == 2


@pytest.mark.asyncio
async def test_media_path_video_enrichment_exception_is_soft() -> None:
    page_row = SimpleNamespace(
        id=uuid4(),
        page_number=1,
        start_ms=0,
        end_ms=60_000,
        markdown_content="# Transcript (chunk 1)\n\nhello world enough text here",
    )
    repo = AsyncMock()
    repo.create_source_page = AsyncMock(return_value=page_row)
    repo.update_status = AsyncMock()
    enrich_instance = AsyncMock()
    enrich_instance.enrich = AsyncMock(side_effect=RuntimeError("total failure"))

    with (
        patch(
            "platform_service.workers.extractors.stage_a_media_path.assemble_outline_from_page_pairs",
            AsyncMock(return_value=0),
        ),
        patch(
            "platform_service.workers.extractors.stage_a_media_path.assert_document_has_text",
            AsyncMock(),
        ),
        patch(
            "platform_service.workers.extractors.stage_a_media_path.VideoVisualEnrichmentService",
            return_value=enrich_instance,
        ),
    ):
        result = await run_media_transcript_path(
            repo,
            AsyncMock(),
            source_document_id=uuid4(),
            text_pages=[
                ExtractedPage(
                    page_number=1,
                    markdown="# Transcript (chunk 1)\n\nhello world enough text here",
                    start_ms=0,
                    end_ms=60_000,
                    extraction_quality_score=0.9,
                )
            ],
            total_pages=1,
            primary_language="bn",
            source_path="/tmp/v.mp4",
            source_type="video",
            vision_extractor=MagicMock(),
        )

    assert result.extraction_method_counts == {"transcript": 1}
    repo.update_status.assert_awaited()


@pytest.mark.asyncio
async def test_media_path_video_empty_audio_logs_and_still_enriches(
    caplog: pytest.LogCaptureFixture,
) -> None:
    page_row = SimpleNamespace(
        id=uuid4(),
        page_number=1,
        start_ms=0,
        end_ms=60_000,
        markdown_content="",
    )
    repo = AsyncMock()
    repo.create_source_page = AsyncMock(return_value=page_row)
    repo.update_status = AsyncMock()
    enrich_instance = AsyncMock()

    async def _enrich(*, source_document_id, source_path, pages):  # noqa: ANN001
        pages[0].markdown_content = (
            "## Visual (t=0ms)\n\nA slide about diabetes prevention with enough characters to pass."
        )
        return 1

    enrich_instance.enrich = AsyncMock(side_effect=_enrich)
    captured_markdowns: list[str] = []

    async def _capture_guard(*_args, page_markdowns, **_kwargs):  # noqa: ANN001
        captured_markdowns.extend(list(page_markdowns))

    with (
        patch(
            "platform_service.workers.extractors.stage_a_media_path.assemble_outline_from_page_pairs",
            AsyncMock(return_value=0),
        ),
        patch(
            "platform_service.workers.extractors.stage_a_media_path.assert_document_has_text",
            side_effect=_capture_guard,
        ),
        patch(
            "platform_service.workers.extractors.stage_a_media_path.VideoVisualEnrichmentService",
            return_value=enrich_instance,
        ),
        caplog.at_level("INFO"),
    ):
        result = await run_media_transcript_path(
            repo,
            AsyncMock(),
            source_document_id=uuid4(),
            text_pages=[
                ExtractedPage(
                    page_number=1,
                    markdown="",
                    start_ms=0,
                    end_ms=60_000,
                    extraction_quality_score=0.0,
                )
            ],
            total_pages=1,
            primary_language="bn",
            source_path="/tmp/v.mp4",
            source_type="video",
            vision_extractor=MagicMock(),
        )

    enrich_instance.enrich.assert_awaited_once()
    assert result.extraction_method_counts["video_visual"] == 1
    assert any("empty-audio fallback" in rec.message for rec in caplog.records)
    assert captured_markdowns
    assert "Visual" in captured_markdowns[0]
    assert "diabetes" in captured_markdowns[0]
