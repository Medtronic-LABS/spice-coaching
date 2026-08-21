"""Sample frames from a video for Stage A visual enrichment.

Planning is pure (no ffmpeg). Extraction reuses timestamped PNG grab from
``media_thumbnail.render_video_frame_to_png``.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from platform_service.workers.extractors.media_thumbnail import (
    MediaThumbnailError,
    render_video_frame_to_png,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TimeRange:
    """Inclusive-start exclusive-end window in milliseconds (chunk bounds)."""

    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class SampledFrame:
    """One sampled video frame ready for vision + persistence."""

    start_ms: int
    end_ms: int
    png_bytes: bytes
    content_sha256: str


def plan_frame_timestamps(
    ranges: Sequence[TimeRange],
    *,
    interval_ms: int,
    max_frames: int,
) -> list[int]:
    """Return wall-clock sample timestamps within ``ranges``.

    For each range, emits ``start_ms + k * interval_ms`` while ``< end_ms``.
    Stops once ``max_frames`` timestamps are collected across all ranges.
    """
    if interval_ms <= 0:
        raise ValueError(f"interval_ms must be > 0, got {interval_ms}")
    if max_frames <= 0:
        return []

    timestamps: list[int] = []
    seen: set[int] = set()
    for window in ranges:
        if window.end_ms <= window.start_ms:
            continue
        t = window.start_ms
        while t < window.end_ms:
            if t not in seen:
                timestamps.append(t)
                seen.add(t)
                if len(timestamps) >= max_frames:
                    return timestamps
            t += interval_ms
    return timestamps


def format_visual_heading(start_ms: int) -> str:
    """Render ``## Visual (t=MM:SS)`` or ``## Visual (t=H:MM:SS)`` for long videos."""
    total_seconds = max(0, start_ms) // 1000
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"## Visual (t={hours}:{minutes:02d}:{seconds:02d})"
    return f"## Visual (t={minutes:02d}:{seconds:02d})"


def append_visual_section(base_markdown: str, *, start_ms: int, vision_markdown: str) -> str:
    """Append a visual heading + body to transcript markdown; skip empty vision."""
    body = vision_markdown.strip()
    if not body:
        return base_markdown
    section = f"{format_visual_heading(start_ms)}\n\n{body}"
    base = base_markdown.rstrip()
    if not base:
        return section
    return f"{base}\n\n{section}"


def sample_video_frames(
    source_path: str | Path,
    ranges: Sequence[TimeRange],
    *,
    interval_ms: int = 30_000,
    max_frames: int = 40,
) -> list[SampledFrame]:
    """Extract PNG frames at planned timestamps; skip duplicate SHA-256 payloads."""
    path = Path(source_path)
    timestamps = plan_frame_timestamps(ranges, interval_ms=interval_ms, max_frames=max_frames)
    if not timestamps:
        return []

    frames: list[SampledFrame] = []
    seen_sha: set[str] = set()
    for ts in timestamps:
        try:
            png_bytes = _extract_frame_png_bytes(path, timestamp_ms=ts)
        except MediaThumbnailError:
            logger.warning(
                "video frame sample failed path=%s timestamp_ms=%d",
                path,
                ts,
                exc_info=True,
            )
            continue
        if not png_bytes:
            continue
        digest = hashlib.sha256(png_bytes).hexdigest()
        if digest in seen_sha:
            continue
        seen_sha.add(digest)
        # Point frame: start_ms == end_ms; assigner treats as instant within page window.
        frames.append(
            SampledFrame(
                start_ms=ts,
                end_ms=ts,
                png_bytes=png_bytes,
                content_sha256=digest,
            )
        )
        if len(frames) >= max_frames:
            break
    return frames


def _extract_frame_png_bytes(source_path: Path, *, timestamp_ms: int) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        dest = Path(tmp.name)
    try:
        render_video_frame_to_png(source_path, dest_path=dest, timestamp_ms=timestamp_ms)
        return dest.read_bytes()
    finally:
        dest.unlink(missing_ok=True)


__all__ = [
    "TimeRange",
    "SampledFrame",
    "plan_frame_timestamps",
    "format_visual_heading",
    "append_visual_section",
    "sample_video_frames",
]
