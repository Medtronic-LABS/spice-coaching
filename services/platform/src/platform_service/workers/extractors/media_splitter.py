"""Server-side AV splitter — produces ~2-minute audio chunks with deterministic timecodes.

The 2-minute window is short enough that downstream transcription does
not need to reason about timestamps inside the chunk; the canonical
``(start_ms, end_ms)`` for every transcript page is computed here from
the splitter parameters, never from the LLM.

Implementation notes:

- Uses ``ffmpeg`` / ``ffprobe`` via subprocess (the platform image
  installs ffmpeg in its apt layer). The Python wrapper keeps the call
  surface narrow — one ``split_into_chunks`` entry point — so tests
  mock the binary instead of running it.
- Always re-encodes to ``audio/mp3`` at 64 kbps mono. This makes
  per-chunk payloads small (under Gemini's inline transcription cap)
  and consistent regardless of source container/codec; the CPU cost
  is negligible at the platform's volume. Gemini requires ``audio/mp3``
  (not ``audio/mpeg``) for inline MP3 parts.
- Audio sources skip video stream selection entirely; video sources
  drop video via ``-vn`` before encoding audio.
"""

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from platform_service.services.media_duration import (
    MediaDurationError,
    probe_media_duration_ms,
    probe_media_has_audio_stream,
)

logger = logging.getLogger(__name__)

# Gemini rejects near-empty inline MP3 (header-only / tens of ms). At 64 kbps
# mono, 4 KiB is ~0.5s of audio — enough for a real frame payload, small
# enough that silent remnant windows from duration-vs-stream mismatch drop out.
MIN_TRANSCRIBABLE_CHUNK_BYTES = 4_096


class MediaSplitterError(RuntimeError):
    """Raised when ffmpeg/ffprobe fails or media duration cannot be determined."""

    def __init__(self, message: str, *, reason: str = "media_unreadable") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class MediaChunk:
    """One window of an AV source with deterministic timecodes."""

    index: int  # 0-based chunk index among kept (transcribable) chunks
    start_ms: int
    end_ms: int
    payload_bytes: bytes
    mime_type: str  # always "audio/mp3" for now


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise MediaSplitterError(
            f"{name!r} not found on PATH; install ffmpeg in the platform image",
            reason="media_unreadable",
        )
    return path


def _probe_duration_ms(source_path: Path) -> int:
    """Return the source's total duration in milliseconds via ffprobe."""
    try:
        return probe_media_duration_ms(source_path)
    except MediaDurationError as exc:
        raise MediaSplitterError(str(exc)) from exc


def iter_media_time_windows(
    total_duration_ms: int,
    *,
    chunk_duration_ms: int = 120_000,
    overlap_ms: int = 15_000,
) -> list[tuple[int, int]]:
    """Return ``(start_ms, end_ms)`` windows matching ``split_into_chunks`` math.

    Used for visual-only video fallback when every encoded audio window is
    undersized and no ``MediaChunk`` payloads exist.
    """
    if chunk_duration_ms <= overlap_ms:
        raise ValueError("chunk_duration_ms must be greater than overlap_ms")
    if total_duration_ms <= 0:
        return []

    step_ms = chunk_duration_ms - overlap_ms
    windows: list[tuple[int, int]] = []
    start_ms = 0
    while start_ms < total_duration_ms:
        window_ms = min(chunk_duration_ms, total_duration_ms - start_ms)
        windows.append((start_ms, start_ms + window_ms))
        if start_ms + window_ms >= total_duration_ms:
            break
        start_ms += step_ms
    return windows


def _encode_chunk(
    source_path: Path,
    *,
    start_ms: int,
    duration_ms: int,
    is_video: bool,
    dest: Path,
) -> None:
    """Encode one chunk to mp3 64 kbps mono. Raises ``MediaSplitterError`` on failure."""
    ffmpeg = _require_binary("ffmpeg")
    cmd: list[str] = [
        ffmpeg,
        "-loglevel",
        "error",
        "-ss",
        f"{start_ms / 1000:.3f}",
        "-i",
        str(source_path),
        "-t",
        f"{duration_ms / 1000:.3f}",
    ]
    if is_video:
        cmd.append("-vn")
    cmd.extend(
        [
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "64k",
            "-codec:a",
            "libmp3lame",
            "-y",
            str(dest),
        ]
    )
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        raise MediaSplitterError(
            f"ffmpeg chunk encode failed (start_ms={start_ms}): {exc.stderr.strip()}",
            reason="media_encode_failed",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaSplitterError(
            f"ffmpeg chunk encode timed out (start_ms={start_ms})",
            reason="media_encode_timeout",
        ) from exc


def split_into_chunks(
    source_path: str | Path,
    *,
    source_type: str,
    chunk_duration_ms: int = 120_000,
    overlap_ms: int = 15_000,
    min_chunk_bytes: int = MIN_TRANSCRIBABLE_CHUNK_BYTES,
) -> list[MediaChunk]:
    """Split an audio/video file into mp3 chunks with deterministic timecodes.

    Sources shorter than ``chunk_duration_ms`` produce a single chunk that
    spans the whole source. The step between chunk starts is
    ``chunk_duration_ms - overlap_ms`` so a sentence straddling a boundary
    appears in both neighbours (downstream can tolerate the slight
    duplication; at this scale it is acceptable).

    Encoded windows smaller than ``min_chunk_bytes`` are dropped — typically
    residual seeks past real audio when container duration exceeds the stream.
    Raises ``MediaSplitterError`` when every window is undersized.
    """
    if chunk_duration_ms <= overlap_ms:
        raise ValueError("chunk_duration_ms must be greater than overlap_ms")
    if source_type not in {"audio", "video"}:
        raise ValueError(f"unsupported source_type for splitter: {source_type!r}")
    if min_chunk_bytes < 1:
        raise ValueError("min_chunk_bytes must be >= 1")

    path = Path(source_path)
    if not path.is_file():
        raise MediaSplitterError(f"media file not found: {path}", reason="media_file_not_found")

    total_duration_ms = _probe_duration_ms(path)
    if total_duration_ms <= 0:
        raise MediaSplitterError(
            f"media has non-positive duration: {path.name}",
            reason="media_no_duration",
        )

    if source_type == "video":
        try:
            has_audio = probe_media_has_audio_stream(path)
        except MediaDurationError as exc:
            raise MediaSplitterError(str(exc)) from exc
        if not has_audio:
            raise MediaSplitterError(
                f"no transcribable audio chunks for {path.name}: video has no audio stream",
                reason="media_unreadable",
            )

    windows = iter_media_time_windows(
        total_duration_ms,
        chunk_duration_ms=chunk_duration_ms,
        overlap_ms=overlap_ms,
    )
    step_ms = chunk_duration_ms - overlap_ms
    chunks: list[MediaChunk] = []
    skipped_undersized = 0
    with tempfile.TemporaryDirectory(prefix="media_split_") as tmpdir:
        tmp_root = Path(tmpdir)
        for encode_index, (start_ms, end_ms) in enumerate(windows):
            window_ms = end_ms - start_ms
            chunk_path = tmp_root / f"chunk_{encode_index:04d}.mp3"
            _encode_chunk(
                path,
                start_ms=start_ms,
                duration_ms=window_ms,
                is_video=(source_type == "video"),
                dest=chunk_path,
            )
            payload = chunk_path.read_bytes()
            if len(payload) < min_chunk_bytes:
                skipped_undersized += 1
                logger.warning(
                    "Skipping undersized media chunk %s start_ms=%d window_ms=%d bytes=%d min_bytes=%d",
                    path.name,
                    start_ms,
                    window_ms,
                    len(payload),
                    min_chunk_bytes,
                )
            else:
                chunks.append(
                    MediaChunk(
                        index=len(chunks),
                        start_ms=start_ms,
                        end_ms=end_ms,
                        payload_bytes=payload,
                        mime_type="audio/mp3",
                    )
                )

    if not chunks:
        raise MediaSplitterError(
            f"no transcribable audio chunks for {path.name}: "
            f"all {skipped_undersized} encoded window(s) were below "
            f"{min_chunk_bytes} bytes",
            reason="media_unreadable",
        )

    logger.info(
        "Media split %s: duration=%dms chunks=%d skipped_undersized=%d "
        "step=%dms overlap=%dms min_chunk_bytes=%d",
        path.name,
        total_duration_ms,
        len(chunks),
        skipped_undersized,
        step_ms,
        overlap_ms,
        min_chunk_bytes,
    )
    return chunks
