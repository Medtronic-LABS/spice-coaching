"""Unit tests for ingestion user-facing error message mapping."""

from __future__ import annotations

from mc_contracts.errors import ErrorCode
from platform_service.services.ingest_step_errors import build_step_failure
from platform_service.services.ingest_user_error_messages import user_message_for_step


class TestUserMessageForStep:
    def test_reason_document_empty(self) -> None:
        message = user_message_for_step(
            error_code=ErrorCode.EXTRACT_FAILED.value,
            error_jsonb={"reason": "document_empty"},
        )
        assert message == ("The document appears to be empty or has too little text to process.")

    def test_reason_media_encode_failed(self) -> None:
        message = user_message_for_step(
            error_code=ErrorCode.EXTRACT_FAILED.value,
            error_jsonb={"reason": "media_encode_failed"},
        )
        assert "couldn't process the audio" in message

    def test_heuristic_ffmpeg_legacy_row(self) -> None:
        message = user_message_for_step(
            error_code=ErrorCode.EXTRACT_FAILED.value,
            technical_message=(
                "ffmpeg chunk encode failed (start_ms=0): Invalid data found when processing input"
            ),
        )
        assert "couldn't process the audio" in message
        assert "ffmpeg" not in message

    def test_error_code_identify_no_candidates(self) -> None:
        message = user_message_for_step(error_code=ErrorCode.IDENTIFY_NO_CANDIDATES.value)
        assert "couldn't find any training modules" in message

    def test_generic_fallback(self) -> None:
        message = user_message_for_step(
            error_code=ErrorCode.STAGE_FAILED.value,
            technical_message="something totally unknown happened",
        )
        assert "Something went wrong while processing this file" in message


class TestBuildStepFailure:
    def test_splits_user_message_and_detail(self) -> None:
        exc = RuntimeError("ffmpeg chunk encode failed (start_ms=0): bad data")
        user_message, error = build_step_failure(
            error_code=ErrorCode.EXTRACT_FAILED.value,
            exc=exc,
            reason="media_encode_failed",
        )
        assert "couldn't process the audio" in user_message
        assert error["detail"] == str(exc)
        assert error["reason"] == "media_encode_failed"
        assert error["type"] == "RuntimeError"
        assert "message" not in error

    def test_document_empty_exception(self) -> None:
        from platform_service.workers.stage_a_types import Stage1DocumentEmptyError

        exc = Stage1DocumentEmptyError()
        user_message, error = build_step_failure(
            error_code=ErrorCode.EXTRACT_FAILED.value,
            exc=exc,
            reason=exc.reason,
            stage="extract",
        )
        assert user_message == ("The document appears to be empty or has too little text to process.")
        assert error["detail"] == "The document is empty."
