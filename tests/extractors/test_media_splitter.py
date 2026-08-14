"""Unit tests for the 2-minute AV media splitter.

ffmpeg / ffprobe are mocked via ``subprocess.run`` so the tests run
without the binaries installed.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from platform_service.workers.extractors.media_splitter import (
    MIN_TRANSCRIBABLE_CHUNK_BYTES,
    MediaSplitterError,
    iter_media_time_windows,
    split_into_chunks,
)

_VALID_PAYLOAD = b"m" * MIN_TRANSCRIBABLE_CHUNK_BYTES


def _fake_run(
    duration_seconds: float,
    *,
    encode_payload: bytes = _VALID_PAYLOAD,
    encode_payloads_by_call: list[bytes] | None = None,
    has_audio_stream: bool = True,
) -> MagicMock:
    """A subprocess.run replacement that fakes ffprobe + ffmpeg calls.

    When ``encode_payloads_by_call`` is set, the Nth ffmpeg write uses that
    list entry (falling back to ``encode_payload`` if the list is short).
    """
    chunk_writes: list[Path] = []
    encode_call = 0

    def runner(cmd: list[str], **kwargs):
        nonlocal encode_call
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        if cmd[0].endswith("ffprobe"):
            if "-select_streams" in cmd:
                result.stdout = "0\n" if has_audio_stream else ""
            else:
                result.stdout = f'{{"format": {{"duration": "{duration_seconds}"}}}}'
        else:
            # ffmpeg: write fake payload to the destination path (last arg).
            dest = Path(cmd[-1])
            if encode_payloads_by_call is not None and encode_call < len(encode_payloads_by_call):
                payload = encode_payloads_by_call[encode_call]
            else:
                payload = encode_payload
            dest.write_bytes(payload)
            chunk_writes.append(dest)
            encode_call += 1
            result.stdout = ""
        return result

    return MagicMock(side_effect=runner), chunk_writes


def _patch_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    def which(name: str) -> str:
        return f"/fake/bin/{name}"

    monkeypatch.setattr("platform_service.services.media_duration.shutil.which", which)
    monkeypatch.setattr(
        "platform_service.workers.extractors.media_splitter.shutil.which",
        which,
    )


def _patch_subprocess(monkeypatch: pytest.MonkeyPatch, fake: MagicMock) -> None:
    monkeypatch.setattr("platform_service.services.media_duration.subprocess.run", fake)
    monkeypatch.setattr(
        "platform_service.workers.extractors.media_splitter.subprocess.run",
        fake,
    )


def test_short_source_produces_single_chunk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_binaries(monkeypatch)
    source = tmp_path / "audio.mp3"
    source.write_bytes(b"x")
    fake, _ = _fake_run(duration_seconds=30.0)
    _patch_subprocess(monkeypatch, fake)

    chunks = split_into_chunks(source, source_type="audio")

    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].start_ms == 0
    assert chunks[0].end_ms == 30_000
    assert chunks[0].mime_type == "audio/mp3"
    assert chunks[0].payload_bytes == _VALID_PAYLOAD


def test_long_source_chunks_with_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_binaries(monkeypatch)
    source = tmp_path / "video.mp4"
    source.write_bytes(b"x")
    # 5 minutes (300s) of media → with 120s chunks and 15s overlap (step=105s):
    #   chunk 0: 0–120000
    #   chunk 1: 105000–225000
    #   chunk 2: 210000–300000 (clipped to source end)
    fake, _ = _fake_run(duration_seconds=300.0)
    _patch_subprocess(monkeypatch, fake)

    chunks = split_into_chunks(source, source_type="video")

    assert [(c.start_ms, c.end_ms) for c in chunks] == [
        (0, 120_000),
        (105_000, 225_000),
        (210_000, 300_000),
    ]
    assert [c.index for c in chunks] == [0, 1, 2]


def test_undersized_trailing_chunk_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Near-empty encode (e.g. seek past real audio) must not be returned."""
    _patch_binaries(monkeypatch)
    source = tmp_path / "v.mp4"
    source.write_bytes(b"x")
    # Two windows for ~210s with default step; second encode is junk (425 B).
    fake, _ = _fake_run(
        duration_seconds=210.0,
        encode_payloads_by_call=[_VALID_PAYLOAD, b"x" * 425],
    )
    _patch_subprocess(monkeypatch, fake)

    chunks = split_into_chunks(source, source_type="video")

    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].start_ms == 0
    assert chunks[0].end_ms == 120_000


def test_all_undersized_chunks_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_binaries(monkeypatch)
    source = tmp_path / "tiny.mp3"
    source.write_bytes(b"x")
    fake, _ = _fake_run(duration_seconds=0.05, encode_payload=b"x" * 425)
    _patch_subprocess(monkeypatch, fake)

    with pytest.raises(MediaSplitterError, match="no transcribable audio chunks"):
        split_into_chunks(source, source_type="audio")


def test_video_without_audio_stream_raises_no_transcribable_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_binaries(monkeypatch)
    source = tmp_path / "visual_only.mp4"
    source.write_bytes(b"x")
    fake, _ = _fake_run(duration_seconds=60.0, has_audio_stream=False)
    _patch_subprocess(monkeypatch, fake)

    with pytest.raises(MediaSplitterError, match="no transcribable audio chunks"):
        split_into_chunks(source, source_type="video")

    ffmpeg_calls = [call for call in fake.call_args_list if call.args[0][0].endswith("ffmpeg")]
    assert ffmpeg_calls == []


def test_video_source_passes_vn_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Video sources must drop the video stream before encoding."""
    _patch_binaries(monkeypatch)
    source = tmp_path / "v.mp4"
    source.write_bytes(b"x")
    fake, _ = _fake_run(duration_seconds=60.0)
    _patch_subprocess(monkeypatch, fake)

    split_into_chunks(source, source_type="video")

    # First call is ffprobe; subsequent calls are ffmpeg.
    ffmpeg_calls = [call for call in fake.call_args_list if call.args[0][0].endswith("ffmpeg")]
    assert ffmpeg_calls, "ffmpeg was not invoked"
    for call in ffmpeg_calls:
        assert "-vn" in call.args[0]


def test_audio_source_does_not_pass_vn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_binaries(monkeypatch)
    source = tmp_path / "a.mp3"
    source.write_bytes(b"x")
    fake, _ = _fake_run(duration_seconds=60.0)
    _patch_subprocess(monkeypatch, fake)

    split_into_chunks(source, source_type="audio")

    ffmpeg_calls = [call for call in fake.call_args_list if call.args[0][0].endswith("ffmpeg")]
    for call in ffmpeg_calls:
        assert "-vn" not in call.args[0]


def test_missing_binary_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform_service.services.media_duration.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "platform_service.workers.extractors.media_splitter.shutil.which",
        lambda name: None,
    )
    source = tmp_path / "x.mp3"
    source.write_bytes(b"x")
    with pytest.raises(MediaSplitterError, match="not found on PATH"):
        split_into_chunks(source, source_type="audio")


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(MediaSplitterError, match="media file not found"):
        split_into_chunks(tmp_path / "nope.mp3", source_type="audio")


def test_zero_duration_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_binaries(monkeypatch)
    source = tmp_path / "x.mp3"
    source.write_bytes(b"x")
    fake, _ = _fake_run(duration_seconds=0.0)
    _patch_subprocess(monkeypatch, fake)

    with pytest.raises(MediaSplitterError, match="non-positive duration"):
        split_into_chunks(source, source_type="audio")


def test_unsupported_source_type_raises(tmp_path: Path) -> None:
    source = tmp_path / "x.pdf"
    source.write_bytes(b"x")
    with pytest.raises(ValueError, match="unsupported source_type"):
        split_into_chunks(source, source_type="pdf")


def test_chunk_duration_must_exceed_overlap() -> None:
    with pytest.raises(ValueError, match="must be greater than overlap"):
        split_into_chunks("/tmp/x", source_type="audio", chunk_duration_ms=60_000, overlap_ms=60_000)


def test_iter_media_time_windows_short_source() -> None:
    assert iter_media_time_windows(30_000) == [(0, 30_000)]


def test_iter_media_time_windows_matches_split_overlap() -> None:
    assert iter_media_time_windows(300_000) == [
        (0, 120_000),
        (105_000, 225_000),
        (210_000, 300_000),
    ]


def test_iter_media_time_windows_non_positive_is_empty() -> None:
    assert iter_media_time_windows(0) == []
    assert iter_media_time_windows(-1) == []


def test_iter_media_time_windows_rejects_bad_overlap() -> None:
    with pytest.raises(ValueError, match="must be greater than overlap"):
        iter_media_time_windows(60_000, chunk_duration_ms=60_000, overlap_ms=60_000)
