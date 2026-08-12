"""Unit tests for the chunked AV ``MediaSourceExtractor``."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from platform_service.workers.extractors.media_extractor import MediaSourceExtractor
from platform_service.workers.extractors.media_splitter import (
    MIN_TRANSCRIBABLE_CHUNK_BYTES,
    MediaChunk,
    MediaSplitterError,
)
from platform_service.workers.extractors.text_extractor import TextExtractionError

pytestmark = pytest.mark.asyncio

_VALID_PAYLOAD = b"x" * MIN_TRANSCRIBABLE_CHUNK_BYTES


def _chunk(
    index: int,
    start_ms: int,
    end_ms: int,
    payload: bytes = _VALID_PAYLOAD,
) -> MediaChunk:
    return MediaChunk(
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        payload_bytes=payload,
        mime_type="audio/mp3",
    )


async def test_one_chunk_one_extracted_page_with_timecodes() -> None:
    splitter = MagicMock(return_value=[_chunk(0, 0, 30_000)])
    transcribe = AsyncMock(return_value="Hello world this is a sentence with enough words")
    ext = MediaSourceExtractor(splitter_fn=splitter, transcribe_fn=transcribe)

    result = await ext.extract("/tmp/x.mp3", source_type="audio", primary_language="bn")

    assert result.requires_calibration is False
    assert result.extraction_method_label == "transcript"
    assert len(result.pages) == 1
    page = result.pages[0]
    assert page.page_number == 1
    assert page.start_ms == 0
    assert page.end_ms == 30_000
    assert "Hello world" in page.markdown
    assert page.markdown.startswith("# Transcript (chunk 1)")
    # Quality must be non-trivial for a >5-word transcript.
    assert page.extraction_quality_score is not None
    assert page.extraction_quality_score >= 0.5


async def test_many_chunks_produce_sequential_pages() -> None:
    splitter = MagicMock(
        return_value=[
            _chunk(0, 0, 120_000),
            _chunk(1, 105_000, 225_000),
            _chunk(2, 210_000, 300_000),
        ]
    )
    transcribe = AsyncMock(return_value="A reasonably long transcript with several words present.")
    ext = MediaSourceExtractor(splitter_fn=splitter, transcribe_fn=transcribe)

    result = await ext.extract("/tmp/v.mp4", source_type="video", primary_language="bn")

    assert [p.page_number for p in result.pages] == [1, 2, 3]
    assert [(p.start_ms, p.end_ms) for p in result.pages] == [
        (0, 120_000),
        (105_000, 225_000),
        (210_000, 300_000),
    ]
    assert transcribe.await_count == 3


async def test_empty_transcript_records_empty_page_with_zero_quality() -> None:
    """A chunk that came back as silence should land as a low-quality page,
    not crash the run — the downstream insufficient_source_filter handles it."""
    splitter = MagicMock(return_value=[_chunk(0, 0, 60_000)])
    transcribe = AsyncMock(return_value="   ")
    ext = MediaSourceExtractor(splitter_fn=splitter, transcribe_fn=transcribe)

    result = await ext.extract("/tmp/x.mp3", source_type="audio", primary_language="bn")

    page = result.pages[0]
    assert page.markdown == ""
    assert page.extraction_quality_score == 0.0


async def test_undersized_chunk_skips_transcription() -> None:
    """Near-empty payloads must not hit Gemini — empty page, quality 0."""
    tiny = b"x" * 425
    assert len(tiny) < MIN_TRANSCRIBABLE_CHUNK_BYTES
    splitter = MagicMock(
        return_value=[
            _chunk(0, 0, 120_000),
            _chunk(1, 105_000, 210_000, payload=tiny),
        ]
    )
    transcribe = AsyncMock(return_value="spoken words from the first chunk only here")
    ext = MediaSourceExtractor(splitter_fn=splitter, transcribe_fn=transcribe)

    result = await ext.extract("/tmp/x.mp4", source_type="video", primary_language="bn")

    assert transcribe.await_count == 1
    transcribe.assert_awaited_once_with(_VALID_PAYLOAD, "audio/mp3")
    assert result.pages[0].markdown.startswith("# Transcript (chunk 1)")
    assert result.pages[1].markdown == ""
    assert result.pages[1].extraction_quality_score == 0.0
    assert result.pages[1].start_ms == 105_000
    assert result.pages[1].end_ms == 210_000


async def test_splitter_error_becomes_text_extraction_error() -> None:
    def boom(*args, **kwargs):
        raise MediaSplitterError("ffmpeg not available")

    ext = MediaSourceExtractor(splitter_fn=boom, transcribe_fn=AsyncMock())
    with pytest.raises(TextExtractionError, match="ffmpeg not available"):
        await ext.extract("/tmp/x.mp3", source_type="audio", primary_language="bn")


async def test_empty_chunk_list_raises_text_extraction_error() -> None:
    splitter = MagicMock(return_value=[])
    ext = MediaSourceExtractor(splitter_fn=splitter, transcribe_fn=AsyncMock())
    with pytest.raises(TextExtractionError, match="no chunks"):
        await ext.extract("/tmp/x.mp3", source_type="audio", primary_language="bn")


async def test_transcribe_fn_receives_chunk_bytes_and_mime_type() -> None:
    payload = b"c" * MIN_TRANSCRIBABLE_CHUNK_BYTES
    splitter = MagicMock(return_value=[_chunk(0, 0, 30_000, payload=payload)])
    transcribe = AsyncMock(return_value="some text")
    ext = MediaSourceExtractor(splitter_fn=splitter, transcribe_fn=transcribe)

    await ext.extract("/tmp/x.mp3", source_type="audio", primary_language="bn")

    transcribe.assert_awaited_once_with(payload, "audio/mp3")


async def test_video_empty_transcript_app_error_becomes_empty_timed_page() -> None:
    splitter = MagicMock(return_value=[_chunk(0, 0, 60_000), _chunk(1, 45_000, 90_000)])
    transcribe = AsyncMock(
        side_effect=AppError(
            ErrorCode.EMPTY_TRANSCRIPT.value,
            "provider returned empty transcript",
            status=422,
        )
    )
    ext = MediaSourceExtractor(splitter_fn=splitter, transcribe_fn=transcribe)

    result = await ext.extract("/tmp/v.mp4", source_type="video", primary_language="bn")

    assert len(result.pages) == 2
    assert all(page.markdown == "" for page in result.pages)
    assert [(p.start_ms, p.end_ms) for p in result.pages] == [
        (0, 60_000),
        (45_000, 90_000),
    ]
    assert all(page.extraction_quality_score == 0.0 for page in result.pages)
    assert transcribe.await_count == 2


async def test_audio_empty_transcript_app_error_still_raises() -> None:
    splitter = MagicMock(return_value=[_chunk(0, 0, 60_000)])
    transcribe = AsyncMock(
        side_effect=AppError(
            ErrorCode.EMPTY_TRANSCRIPT.value,
            "provider returned empty transcript",
            status=422,
        )
    )
    ext = MediaSourceExtractor(splitter_fn=splitter, transcribe_fn=transcribe)

    with pytest.raises(AppError) as exc_info:
        await ext.extract("/tmp/a.mp3", source_type="audio", primary_language="bn")
    assert exc_info.value.code == ErrorCode.EMPTY_TRANSCRIPT.value


async def test_video_non_empty_transcript_app_error_still_raises() -> None:
    splitter = MagicMock(return_value=[_chunk(0, 0, 60_000)])
    transcribe = AsyncMock(
        side_effect=AppError(ErrorCode.AI_RUNTIME_ERROR.value, "provider blew up", status=502)
    )
    ext = MediaSourceExtractor(splitter_fn=splitter, transcribe_fn=transcribe)

    with pytest.raises(AppError) as exc_info:
        await ext.extract("/tmp/v.mp4", source_type="video", primary_language="bn")
    assert exc_info.value.code == ErrorCode.AI_RUNTIME_ERROR.value


async def test_video_no_transcribable_chunks_synthesizes_timed_empty_pages() -> None:
    def boom(*args, **kwargs):
        raise MediaSplitterError(
            "no transcribable audio chunks for mute.mp4: all 3 encoded window(s) were below 4096 bytes"
        )

    ext = MediaSourceExtractor(splitter_fn=boom, transcribe_fn=AsyncMock())
    with patch(
        "platform_service.workers.extractors.media_extractor.probe_media_duration_ms",
        return_value=300_000,
    ):
        result = await ext.extract("/tmp/mute.mp4", source_type="video", primary_language="bn")

    assert result.requires_calibration is False
    assert [(p.start_ms, p.end_ms) for p in result.pages] == [
        (0, 120_000),
        (105_000, 225_000),
        (210_000, 300_000),
    ]
    assert all(page.markdown == "" for page in result.pages)


async def test_audio_no_transcribable_chunks_still_raises() -> None:
    def boom(*args, **kwargs):
        raise MediaSplitterError(
            "no transcribable audio chunks for mute.mp3: all 1 encoded window(s) were below 4096 bytes"
        )

    ext = MediaSourceExtractor(splitter_fn=boom, transcribe_fn=AsyncMock())
    with pytest.raises(TextExtractionError, match="no transcribable audio chunks"):
        await ext.extract("/tmp/mute.mp3", source_type="audio", primary_language="bn")
