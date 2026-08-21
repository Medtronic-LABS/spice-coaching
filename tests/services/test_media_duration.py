"""Unit tests for ffprobe duration probing (binaries mocked)."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from platform_service.services.media_duration import (
    MediaDurationError,
    probe_media_duration_ms,
    probe_media_has_audio_stream,
)


def _patch_ffprobe(monkeypatch: pytest.MonkeyPatch, fake_run: MagicMock) -> None:
    monkeypatch.setattr(
        "platform_service.services.media_duration.shutil.which",
        lambda name: f"/fake/bin/{name}",
    )
    monkeypatch.setattr("platform_service.services.media_duration.subprocess.run", fake_run)


def test_probe_converts_seconds_to_milliseconds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    fake = MagicMock()
    fake.return_value = MagicMock(stdout='{"format": {"duration": "12.345"}}', stderr="")
    _patch_ffprobe(monkeypatch, fake)

    assert probe_media_duration_ms(source) == 12_345
    cmd = fake.call_args.args[0]
    assert cmd[0] == "/fake/bin/ffprobe"
    assert "-show_entries" in cmd
    assert "format=duration" in cmd


def test_probe_missing_binary_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform_service.services.media_duration.shutil.which", lambda name: None)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")

    with pytest.raises(MediaDurationError, match="not found on PATH"):
        probe_media_duration_ms(source)


def test_probe_unparseable_json_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    fake = MagicMock()
    fake.return_value = MagicMock(stdout="not-json", stderr="")
    _patch_ffprobe(monkeypatch, fake)

    with pytest.raises(MediaDurationError, match="unparseable duration"):
        probe_media_duration_ms(source)


def test_probe_missing_duration_field_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    fake = MagicMock()
    fake.return_value = MagicMock(stdout=json.dumps({"format": {}}), stderr="")
    _patch_ffprobe(monkeypatch, fake)

    with pytest.raises(MediaDurationError, match="unparseable duration"):
        probe_media_duration_ms(source)


def test_probe_timeout_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    fake = MagicMock(side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=30))
    _patch_ffprobe(monkeypatch, fake)

    with pytest.raises(MediaDurationError, match="timed out"):
        probe_media_duration_ms(source)


def test_probe_ffprobe_failure_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    fake = MagicMock(
        side_effect=subprocess.CalledProcessError(returncode=1, cmd="ffprobe", stderr="bad codec")
    )
    _patch_ffprobe(monkeypatch, fake)

    with pytest.raises(MediaDurationError, match="ffprobe failed"):
        probe_media_duration_ms(source)


def test_probe_has_audio_stream_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    fake = MagicMock()
    fake.return_value = MagicMock(stdout="0\n", stderr="")
    _patch_ffprobe(monkeypatch, fake)

    assert probe_media_has_audio_stream(source) is True
    cmd = fake.call_args.args[0]
    assert cmd[0] == "/fake/bin/ffprobe"
    assert "-select_streams" in cmd
    assert "a" in cmd


def test_probe_has_audio_stream_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "silent.mp4"
    source.write_bytes(b"x")
    fake = MagicMock()
    fake.return_value = MagicMock(stdout="", stderr="")
    _patch_ffprobe(monkeypatch, fake)

    assert probe_media_has_audio_stream(source) is False


def test_probe_has_audio_stream_ffprobe_failure_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    fake = MagicMock(
        side_effect=subprocess.CalledProcessError(returncode=1, cmd="ffprobe", stderr="bad codec")
    )
    _patch_ffprobe(monkeypatch, fake)

    with pytest.raises(MediaDurationError, match="audio-stream probe failed"):
        probe_media_has_audio_stream(source)
