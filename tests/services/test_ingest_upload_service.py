"""Unit tests for ingest upload helpers (no database required)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from platform_service.config import Settings
from platform_service.services.ingest_errors import IngestValidationError
from platform_service.services.ingest_upload_service import (
    IngestUploadService,
    _StagedIngestUpload,
    duration_ms_for_staged_upload,
    stream_upload_to_path,
)
from platform_service.services.media_duration import MediaDurationError


class _FakeUpload:
    def __init__(self, filename: str, chunks: list[bytes] | None = None) -> None:
        self.filename = filename
        self._chunks = list(chunks or [])

    async def read(self, _size: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


def test_source_type_from_suffix_supports_audio_video() -> None:
    assert IngestUploadService.source_type_from_suffix(".mp3") == "audio"
    assert IngestUploadService.source_type_from_suffix(".wav") == "audio"
    assert IngestUploadService.source_type_from_suffix(".mp4") == "video"
    assert IngestUploadService.source_type_from_suffix(".mov") == "video"


def test_media_upload_limit_bytes_uses_settings() -> None:
    svc = IngestUploadService(MagicMock(), settings=Settings(ingest_media_max_upload_bytes=50_000_000))
    assert svc.media_upload_limit_bytes() == 50_000_000


@pytest.mark.asyncio
async def test_stream_upload_rejects_media_above_limit(tmp_path: Path) -> None:
    upload = _FakeUpload("large.mp3", [b"a" * 6, b"b" * 6])
    dest = tmp_path / "out.bin"

    with pytest.raises(IngestValidationError) as exc_info:
        await stream_upload_to_path(upload, dest, source_type="audio", max_media_bytes=10)

    assert exc_info.value.status_code == 413
    assert not dest.exists()


@pytest.mark.asyncio
async def test_stream_upload_allows_document_above_media_limit(tmp_path: Path) -> None:
    upload = _FakeUpload("large.pdf", [b"a" * 6, b"b" * 6])
    dest = tmp_path / "out.pdf"

    await stream_upload_to_path(upload, dest, source_type="pdf", max_media_bytes=10)

    assert dest.read_bytes() == b"a" * 6 + b"b" * 6


def test_resolve_titles_defaults_to_filename_stems() -> None:
    uploads = [_FakeUpload("BRAC Guide.pdf"), _FakeUpload("uhis-workflow.pptx")]
    assert IngestUploadService.resolve_titles_for_files(None, uploads) == ["BRAC Guide", "uhis-workflow"]


def test_resolve_titles_parses_json_array() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf")]
    assert IngestUploadService.resolve_titles_for_files('["First","Second"]', uploads) == [
        "First",
        "Second",
    ]


def test_resolve_titles_rejects_length_mismatch() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf")]
    with pytest.raises(IngestValidationError) as exc_info:
        IngestUploadService.resolve_titles_for_files('["Only one"]', uploads)
    assert exc_info.value.status_code == 400
    assert "2 entries" in exc_info.value.message


def test_resolve_titles_rejects_invalid_json() -> None:
    uploads = [_FakeUpload("a.pdf")]
    with pytest.raises(IngestValidationError) as exc_info:
        IngestUploadService.resolve_titles_for_files("not-json", uploads)
    assert exc_info.value.status_code == 400


def test_resolve_titles_rejects_empty_string_entry() -> None:
    uploads = [_FakeUpload("a.pdf")]
    with pytest.raises(IngestValidationError) as exc_info:
        IngestUploadService.resolve_titles_for_files('[""]', uploads)
    assert exc_info.value.status_code == 400


def test_resolve_descriptions_defaults_to_none() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf")]
    assert IngestUploadService.resolve_descriptions_for_files(None, uploads) == [None, None]


def test_resolve_descriptions_parses_json_array() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf")]
    assert IngestUploadService.resolve_descriptions_for_files(
        '["First desc", null]',
        uploads,
    ) == ["First desc", None]


def test_resolve_descriptions_rejects_length_mismatch() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf")]
    with pytest.raises(IngestValidationError) as exc_info:
        IngestUploadService.resolve_descriptions_for_files('["Only one"]', uploads)
    assert exc_info.value.status_code == 400


def test_reject_within_batch_duplicate_digests() -> None:
    staged = [
        _StagedIngestUpload(
            staging_path=Path("/tmp/a"),
            content_sha256="same-digest",
            original_filename="a.pdf",
            source_type="pdf",
            title="A",
            description=None,
            override_duplicate=False,
            content_domain="clinical",
        ),
        _StagedIngestUpload(
            staging_path=Path("/tmp/b"),
            content_sha256="same-digest",
            original_filename="b.pdf",
            source_type="pdf",
            title="B",
            description=None,
            override_duplicate=True,
            content_domain="clinical",
        ),
    ]
    with pytest.raises(IngestValidationError) as exc_info:
        IngestUploadService._reject_within_batch_duplicate_digests(staged)
    assert exc_info.value.status_code == 422
    assert "duplicate file content in the same request" in exc_info.value.message


def test_reject_within_batch_allows_distinct_digests() -> None:
    staged = [
        _StagedIngestUpload(
            staging_path=Path("/tmp/a"),
            content_sha256="digest-a",
            original_filename="a.pdf",
            source_type="pdf",
            title="A",
            description=None,
            override_duplicate=False,
            content_domain="clinical",
        ),
        _StagedIngestUpload(
            staging_path=Path("/tmp/b"),
            content_sha256="digest-b",
            original_filename="b.pdf",
            source_type="pdf",
            title="B",
            description=None,
            override_duplicate=False,
            content_domain="clinical",
        ),
    ]
    IngestUploadService._reject_within_batch_duplicate_digests(staged)


def test_resolve_override_duplicates_parses_json_array() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf")]
    assert IngestUploadService.resolve_override_duplicates_for_files("[true, false]", uploads) == [
        True,
        False,
    ]


def test_resolve_override_duplicates_rejects_length_mismatch() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf")]
    with pytest.raises(IngestValidationError) as exc_info:
        IngestUploadService.resolve_override_duplicates_for_files("[true]", uploads)
    assert exc_info.value.status_code == 400
    assert "2 entries" in exc_info.value.message


def test_resolve_override_duplicates_rejects_non_boolean_entry() -> None:
    uploads = [_FakeUpload("a.pdf")]
    with pytest.raises(IngestValidationError) as exc_info:
        IngestUploadService.resolve_override_duplicates_for_files('["yes"]', uploads)
    assert exc_info.value.status_code == 400
    assert "boolean" in exc_info.value.message


def test_resolve_content_domains_defaults_to_clinical() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf")]
    assert IngestUploadService.resolve_content_domains_for_files(None, uploads) == [
        "clinical",
        "clinical",
    ]


def test_resolve_content_domains_parses_json_array() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf")]
    assert IngestUploadService.resolve_content_domains_for_files(
        '["digital","operational"]',
        uploads,
    ) == ["digital", "operational"]


def test_resolve_content_domains_null_and_empty_default_to_clinical() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf"), _FakeUpload("c.pdf")]
    assert IngestUploadService.resolve_content_domains_for_files(
        '[null, "", "  "]',
        uploads,
    ) == ["clinical", "clinical", "clinical"]


def test_resolve_content_domains_rejects_length_mismatch() -> None:
    uploads = [_FakeUpload("a.pdf"), _FakeUpload("b.pdf")]
    with pytest.raises(IngestValidationError) as exc_info:
        IngestUploadService.resolve_content_domains_for_files('["digital"]', uploads)
    assert exc_info.value.status_code == 400
    assert "2 entries" in exc_info.value.message


def test_resolve_content_domains_rejects_invalid_domain() -> None:
    uploads = [_FakeUpload("a.pdf")]
    with pytest.raises(IngestValidationError) as exc_info:
        IngestUploadService.resolve_content_domains_for_files('["not_a_domain"]', uploads)
    assert exc_info.value.status_code == 400
    assert "invalid content_domain" in exc_info.value.message


def test_resolve_content_domains_rejects_non_string_entry() -> None:
    uploads = [_FakeUpload("a.pdf")]
    with pytest.raises(IngestValidationError) as exc_info:
        IngestUploadService.resolve_content_domains_for_files("[true]", uploads)
    assert exc_info.value.status_code == 400
    assert "string or null" in exc_info.value.message


def test_duration_ms_for_staged_upload_probes_video(tmp_path: Path) -> None:
    staging = tmp_path / "clip.mp4"
    staging.write_bytes(b"x")
    with patch(
        "platform_service.services.ingest_upload_service.probe_media_duration_ms",
        return_value=12_345,
    ) as probe:
        assert duration_ms_for_staged_upload(staging, "video") == 12_345
    probe.assert_called_once_with(staging)


def test_duration_ms_for_staged_upload_probes_audio(tmp_path: Path) -> None:
    staging = tmp_path / "clip.mp3"
    staging.write_bytes(b"x")
    with patch(
        "platform_service.services.ingest_upload_service.probe_media_duration_ms",
        return_value=8_000,
    ) as probe:
        assert duration_ms_for_staged_upload(staging, "audio") == 8_000
    probe.assert_called_once_with(staging)


def test_duration_ms_for_staged_upload_skips_pdf(tmp_path: Path) -> None:
    staging = tmp_path / "guide.pdf"
    staging.write_bytes(b"x")
    with patch(
        "platform_service.services.ingest_upload_service.probe_media_duration_ms",
    ) as probe:
        assert duration_ms_for_staged_upload(staging, "pdf") is None
    probe.assert_not_called()


def test_duration_ms_for_staged_upload_probe_failure_returns_none(tmp_path: Path) -> None:
    staging = tmp_path / "clip.mp4"
    staging.write_bytes(b"x")
    with patch(
        "platform_service.services.ingest_upload_service.probe_media_duration_ms",
        side_effect=MediaDurationError("ffprobe failed"),
    ):
        assert duration_ms_for_staged_upload(staging, "video") is None


def test_duration_ms_for_staged_upload_non_positive_returns_none(tmp_path: Path) -> None:
    staging = tmp_path / "clip.mp4"
    staging.write_bytes(b"x")
    with patch(
        "platform_service.services.ingest_upload_service.probe_media_duration_ms",
        return_value=0,
    ):
        assert duration_ms_for_staged_upload(staging, "video") is None
    with patch(
        "platform_service.services.ingest_upload_service.probe_media_duration_ms",
        return_value=-1,
    ):
        assert duration_ms_for_staged_upload(staging, "audio") is None
