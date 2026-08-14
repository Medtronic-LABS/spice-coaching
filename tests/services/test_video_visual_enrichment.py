"""Unit tests for Stage A video visual enrichment (soft-fail)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from platform_service.config import Settings
from platform_service.services.video_visual_enrichment import VideoVisualEnrichmentService
from platform_service.workers.extractors.video_frame_sampler import SampledFrame
from platform_service.workers.extractors.vision_extractor import (
    VisionExtractionError,
    VisionExtractionResult,
)


def _page(*, page_number: int = 1, start_ms: int = 0, end_ms: int = 120_000, markdown: str = "# T\n\nhi"):
    return SimpleNamespace(
        id=uuid4(),
        page_number=page_number,
        start_ms=start_ms,
        end_ms=end_ms,
        markdown_content=markdown,
    )


@pytest.mark.asyncio
async def test_enrich_empty_audio_fallback_runs_when_flag_off() -> None:
    settings = Settings(ingest_video_visual_extraction_enabled=False)
    page = _page()
    frame = SampledFrame(30_000, 30_000, b"\x89PNG frame", "sha1")
    vision = AsyncMock()
    vision.extract_page = AsyncMock(
        return_value=VisionExtractionResult(markdown="Slide title text", raw_response=MagicMock())
    )
    storage = AsyncMock()
    storage.put_object_from_local_file = AsyncMock()
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    svc = VideoVisualEnrichmentService(
        session,
        vision=vision,
        settings=settings,
        storage=storage,
        sample_frames_fn=MagicMock(return_value=[frame]),
    )
    n = await svc.enrich(
        source_document_id=uuid4(),
        source_path="/tmp/v.mp4",
        pages=[page],
        empty_audio_fallback=True,
    )
    assert n == 1
    assert "## Visual (t=00:30)" in page.markdown_content
    vision.extract_page.assert_awaited_once()


@pytest.mark.asyncio
async def test_enrich_flag_off_is_noop() -> None:
    settings = Settings(ingest_video_visual_extraction_enabled=False)
    vision = MagicMock()
    svc = VideoVisualEnrichmentService(
        AsyncMock(),
        vision=vision,
        settings=settings,
        storage=AsyncMock(),
        sample_frames_fn=MagicMock(return_value=[SampledFrame(0, 0, b"png", "abc")]),
    )
    n = await svc.enrich(
        source_document_id=uuid4(),
        source_path="/tmp/v.mp4",
        pages=[_page()],
    )
    assert n == 0
    vision.extract_page.assert_not_called()


@pytest.mark.asyncio
async def test_enrich_appends_markdown_and_persists() -> None:
    settings = Settings(ingest_video_visual_extraction_enabled=True)
    page = _page()
    frame = SampledFrame(30_000, 30_000, b"\x89PNG frame", "sha1")
    vision = AsyncMock()
    vision.extract_page = AsyncMock(
        return_value=VisionExtractionResult(markdown="On-screen BP chart", raw_response=MagicMock())
    )
    storage = AsyncMock()
    storage.put_object_from_local_file = AsyncMock()
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    svc = VideoVisualEnrichmentService(
        session,
        vision=vision,
        settings=settings,
        storage=storage,
        sample_frames_fn=MagicMock(return_value=[frame]),
    )
    n = await svc.enrich(
        source_document_id=uuid4(),
        source_path="/tmp/v.mp4",
        pages=[page],
    )
    assert n == 1
    assert "## Visual (t=00:30)" in page.markdown_content
    assert "On-screen BP chart" in page.markdown_content
    session.add.assert_called_once()
    storage.put_object_from_local_file.assert_awaited()


@pytest.mark.asyncio
async def test_enrich_soft_fails_when_vision_raises() -> None:
    settings = Settings(ingest_video_visual_extraction_enabled=True)
    page = _page(markdown="# Transcript\n\nonly audio")
    frame = SampledFrame(0, 0, b"png", "sha2")
    vision = AsyncMock()
    vision.extract_page = AsyncMock(side_effect=VisionExtractionError("boom"))
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    svc = VideoVisualEnrichmentService(
        session,
        vision=vision,
        settings=settings,
        storage=AsyncMock(),
        sample_frames_fn=MagicMock(return_value=[frame]),
    )
    n = await svc.enrich(
        source_document_id=uuid4(),
        source_path="/tmp/v.mp4",
        pages=[page],
    )
    assert n == 0
    assert page.markdown_content == "# Transcript\n\nonly audio"
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_enrich_soft_fails_when_sampling_raises() -> None:
    settings = Settings(ingest_video_visual_extraction_enabled=True)
    vision = AsyncMock()
    svc = VideoVisualEnrichmentService(
        AsyncMock(),
        vision=vision,
        settings=settings,
        storage=AsyncMock(),
        sample_frames_fn=MagicMock(side_effect=RuntimeError("ffmpeg down")),
    )
    n = await svc.enrich(
        source_document_id=uuid4(),
        source_path="/tmp/v.mp4",
        pages=[_page()],
    )
    assert n == 0
    vision.extract_page.assert_not_called()
