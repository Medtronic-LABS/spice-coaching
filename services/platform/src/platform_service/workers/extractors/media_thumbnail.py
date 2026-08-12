"""AV thumbnail helpers — first video frame or audio waveform PNG via ffmpeg.

Mirrors subprocess conventions from ``media_splitter.py`` so tests can mock
``subprocess.run`` without installing ffmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class MediaThumbnailError(RuntimeError):
    """Raised when ffmpeg fails to produce a thumbnail PNG."""


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise MediaThumbnailError(f"{name!r} not found on PATH; install ffmpeg in the platform image")
    return path


def render_video_frame_to_png(
    source_path: Path,
    *,
    dest_path: Path,
    timestamp_ms: int | None = None,
) -> None:
    """Extract one video frame to ``dest_path``.

    When ``timestamp_ms`` is None (thumbnail path), take the first decodable
    frame. Otherwise seek to that wall-clock offset before grabbing a frame.
    """
    ffmpeg = _require_binary("ffmpeg")
    cmd: list[str] = [ffmpeg, "-loglevel", "error", "-y"]
    if timestamp_ms is not None and timestamp_ms > 0:
        # Input seek for speed; exactness is good enough for sampled vision frames.
        cmd.extend(["-ss", f"{timestamp_ms / 1000.0:.3f}"])
    cmd.extend(["-i", str(source_path)])
    if timestamp_ms is None:
        cmd.extend(["-vf", "select=eq(n\\,0)"])
    cmd.extend(["-vframes", "1", str(dest_path)])
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        raise MediaThumbnailError(
            f"ffmpeg video frame extract failed for {source_path.name}: {exc.stderr.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaThumbnailError(f"ffmpeg video frame extract timed out for {source_path.name}") from exc

    if not dest_path.is_file() or dest_path.stat().st_size == 0:
        raise MediaThumbnailError(f"ffmpeg produced no thumbnail for {source_path.name}: {completed.stderr}")


def render_audio_waveform_to_png(source_path: Path, *, dest_path: Path) -> None:
    """Render a waveform poster image for an audio source."""
    ffmpeg = _require_binary("ffmpeg")
    cmd = [
        ffmpeg,
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-filter_complex",
        "showwavespic=s=640x360:colors=#1a5276",
        "-frames:v",
        "1",
        str(dest_path),
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        raise MediaThumbnailError(
            f"ffmpeg audio waveform failed for {source_path.name}: {exc.stderr.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaThumbnailError(f"ffmpeg audio waveform timed out for {source_path.name}") from exc

    if not dest_path.is_file() or dest_path.stat().st_size == 0:
        raise MediaThumbnailError(f"ffmpeg produced no waveform for {source_path.name}: {completed.stderr}")
