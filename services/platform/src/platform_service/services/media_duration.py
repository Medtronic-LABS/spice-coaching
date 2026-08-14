"""Probe audio/video duration via ffprobe (milliseconds).

Used at ingest upload (persist ``source_document.duration_ms``) and by the
Stage A media splitter. Tests mock ``subprocess.run`` / ``shutil.which``
instead of requiring ffmpeg on PATH.
"""

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class MediaDurationError(RuntimeError):
    """Raised when ffprobe is missing, fails, times out, or returns no duration."""


def _require_ffprobe() -> str:
    path = shutil.which("ffprobe")
    if path is None:
        raise MediaDurationError("'ffprobe' not found on PATH; install ffmpeg in the platform image")
    return path


def probe_media_duration_ms(source_path: str | Path) -> int:
    """Return the source's total duration in milliseconds via ffprobe."""
    path = Path(source_path)
    ffprobe = _require_ffprobe()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
    except subprocess.CalledProcessError as exc:
        raise MediaDurationError(f"ffprobe failed for {path.name}: {exc.stderr.strip()}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaDurationError(f"ffprobe timed out for {path.name}") from exc

    try:
        payload = json.loads(completed.stdout)
        seconds = float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaDurationError(
            f"ffprobe returned unparseable duration for {path.name}: {completed.stdout!r}"
        ) from exc

    return int(seconds * 1000)


def probe_media_has_audio_stream(source_path: str | Path) -> bool:
    """Return True when the file contains at least one audio stream."""
    path = Path(source_path)
    ffprobe = _require_ffprobe()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
    except subprocess.CalledProcessError as exc:
        raise MediaDurationError(
            f"ffprobe audio-stream probe failed for {path.name}: {exc.stderr.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaDurationError(f"ffprobe audio-stream probe timed out for {path.name}") from exc

    return bool(completed.stdout.strip())
