"""User-facing copy for ingestion pipeline step failures."""

from __future__ import annotations

import re
from typing import Any

from mc_contracts.errors import ErrorCode

_GENERIC_FALLBACK = (
    "Something went wrong while processing this file. "
    "Try re-uploading or contact support if the problem persists."
)

_REASON_MESSAGES: dict[str, str] = {
    "document_empty": ("The document appears to be empty or has too little text to process."),
    "vision_recovery_failed": (
        "We couldn't read some pages in this document. Try a clearer scan or re-export the file."
    ),
    "media_unreadable": (
        "We couldn't read the audio or video in this file. "
        "Try re-exporting as MP3 or MP4, or upload a different copy."
    ),
    "media_encode_failed": (
        "We couldn't process the audio in this file. "
        "The file may be corrupted — try re-exporting or uploading again."
    ),
    "media_encode_timeout": (
        "Processing this media file took too long. Try a shorter clip or a smaller file."
    ),
    "media_no_duration": ("This media file has no playable duration. It may be corrupted or incomplete."),
    "media_file_not_found": ("The uploaded media file could not be found. Please re-upload the file."),
    "document_corrupt": (
        "We couldn't open this file. It may be corrupted, password-protected, or in an unsupported format."
    ),
    "document_not_found": ("The uploaded file could not be found. Please re-upload the file."),
    "unsupported_file_type": "This file type isn't supported for ingestion.",
    "identify_no_candidates": (
        "We couldn't find any training modules in this document. "
        "Try a document with clearer sections or headings."
    ),
    "identify_chunks_failed": (
        "We couldn't analyze part of this document. Try re-uploading or simplifying the file structure."
    ),
    "pipeline_crashed": ("Processing was interrupted unexpectedly. Please retry the ingestion."),
    "ai_service_unavailable": ("Our AI service was temporarily unavailable. Please retry in a few minutes."),
    "module_not_found": ("A module required for this step was not found. Please retry the ingestion."),
    "module_has_no_text": ("This module has no text content to process for the next step."),
    "post_publish_failed": (
        "A follow-up step after drafting failed. "
        "The module may still be usable — try retrying from the admin dashboard."
    ),
    "enqueue_failed": ("A background task could not be started. Please retry the ingestion."),
    "thumbnail_failed": "We couldn't generate a preview image for this file.",
    "extract_failed": (
        "We couldn't extract content from this file. Try re-exporting it from the original source."
    ),
    "identify_failed": (
        "We couldn't identify training modules in this document. "
        "Try a document with clearer sections or headings."
    ),
    "draft_failed": (
        "We couldn't draft module cards for one or more candidates. "
        "Try retrying or reviewing the source document."
    ),
    "candidate_merge_failed": (
        "We couldn't merge overlapping module candidates in this batch. Please retry merge."
    ),
    "embedding_failed": ("We couldn't generate search embeddings for this module. Please retry."),
    "generation_failed": ("A content generation step failed. Please retry the ingestion."),
}

_ERROR_CODE_MESSAGES: dict[str, str] = {
    ErrorCode.EXTRACT_FAILED.value: _REASON_MESSAGES["extract_failed"],
    ErrorCode.IDENTIFY_FAILED.value: _REASON_MESSAGES["identify_failed"],
    ErrorCode.IDENTIFY_NO_CANDIDATES.value: _REASON_MESSAGES["identify_no_candidates"],
    ErrorCode.DRAFT_FAILED.value: _REASON_MESSAGES["draft_failed"],
    ErrorCode.CANDIDATE_MERGE_FAILED.value: _REASON_MESSAGES["candidate_merge_failed"],
    ErrorCode.PIPELINE_CRASHED.value: _REASON_MESSAGES["pipeline_crashed"],
    ErrorCode.THUMBNAIL_FAILED.value: _REASON_MESSAGES["thumbnail_failed"],
    ErrorCode.EMBEDDING_FAILED.value: _REASON_MESSAGES["embedding_failed"],
    ErrorCode.GENERATION_FAILED.value: _REASON_MESSAGES["generation_failed"],
    ErrorCode.QUIZ_GENERATION_FAILED.value: _REASON_MESSAGES["generation_failed"],
    ErrorCode.GAP_CLASSIFICATION_FAILED.value: _REASON_MESSAGES["generation_failed"],
    ErrorCode.TRIGGER_BINDING_FAILED.value: _REASON_MESSAGES["generation_failed"],
    ErrorCode.SEARCH_METADATA_FAILED.value: _REASON_MESSAGES["generation_failed"],
    ErrorCode.CARD_SEARCH_METADATA_FAILED.value: _REASON_MESSAGES["generation_failed"],
    ErrorCode.MODULE_NOT_FOUND.value: _REASON_MESSAGES["module_not_found"],
    ErrorCode.MODULE_HAS_NO_TEXT.value: _REASON_MESSAGES["module_has_no_text"],
    ErrorCode.AI_RUNTIME_UNREACHABLE.value: _REASON_MESSAGES["ai_service_unavailable"],
    ErrorCode.AI_RUNTIME_ERROR.value: _REASON_MESSAGES["ai_service_unavailable"],
    ErrorCode.ENQUEUE_FAILED.value: _REASON_MESSAGES["enqueue_failed"],
    ErrorCode.STAGE_FAILED.value: _GENERIC_FALLBACK,
}

_HEURISTIC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ffmpeg chunk encode failed", re.I), "media_encode_failed"),
    (re.compile(r"ffmpeg chunk encode timed out", re.I), "media_encode_timeout"),
    (re.compile(r"ffmpeg.*not found on PATH", re.I), "media_unreadable"),
    (re.compile(r"ffprobe.*not found on PATH", re.I), "media_unreadable"),
    (re.compile(r"media file not found", re.I), "media_file_not_found"),
    (re.compile(r"media has non-positive duration", re.I), "media_no_duration"),
    (re.compile(r"no transcribable audio chunks", re.I), "media_unreadable"),
    (re.compile(r"Failed to open PDF", re.I), "document_corrupt"),
    (re.compile(r"Failed to open PPTX", re.I), "document_corrupt"),
    (re.compile(r"Failed to open DOCX", re.I), "document_corrupt"),
    (re.compile(r"PDF not found|PPTX not found|DOCX not found", re.I), "document_not_found"),
    (re.compile(r"Unsupported source_type", re.I), "unsupported_file_type"),
    (re.compile(r"zero candidates were identified", re.I), "identify_no_candidates"),
    (re.compile(r"module_identify chunks failed", re.I), "identify_chunks_failed"),
    (re.compile(r"chunk failed", re.I), "identify_chunks_failed"),
    (re.compile(r"pipeline crashed", re.I), "pipeline_crashed"),
    (re.compile(r"ai-runtime|ai runtime", re.I), "ai_service_unavailable"),
    (re.compile(r"timeout", re.I), "ai_service_unavailable"),
    (re.compile(r"module .* not found", re.I), "module_not_found"),
    (re.compile(r"failed to enqueue", re.I), "enqueue_failed"),
    (re.compile(r"The document is empty", re.I), "document_empty"),
    (re.compile(r"vision recovery left", re.I), "vision_recovery_failed"),
]


def _as_error_object(error_jsonb: dict[str, Any] | None) -> dict[str, Any]:
    return error_jsonb if isinstance(error_jsonb, dict) else {}


def _message_for_reason(reason: str) -> str | None:
    return _REASON_MESSAGES.get(reason)


def _heuristic_reason(technical_message: str | None) -> str | None:
    if not technical_message or not technical_message.strip():
        return None
    for pattern, reason in _HEURISTIC_PATTERNS:
        if pattern.search(technical_message):
            return reason
    return None


def user_message_for_step(
    *,
    error_code: str | None = None,
    error_jsonb: dict[str, Any] | None = None,
    technical_message: str | None = None,
    stage: str | None = None,
) -> str:
    """Return actionable user-facing copy for a failed ingestion step."""
    err = _as_error_object(error_jsonb)
    reason = err.get("reason")
    if isinstance(reason, str) and reason.strip():
        mapped = _message_for_reason(reason.strip())
        if mapped:
            return mapped

    detail = err.get("detail")
    technical = technical_message
    if not technical and isinstance(detail, str):
        technical = detail
    if not technical and isinstance(err.get("message"), str):
        technical = err["message"]

    heuristic = _heuristic_reason(technical)
    if heuristic:
        mapped = _message_for_reason(heuristic)
        if mapped:
            return mapped

    code = error_code or err.get("code")
    if isinstance(code, str) and code.strip():
        mapped = _ERROR_CODE_MESSAGES.get(code.strip())
        if mapped:
            return mapped

    if stage:
        del stage  # reserved for stage-specific fallbacks in future

    return _GENERIC_FALLBACK
