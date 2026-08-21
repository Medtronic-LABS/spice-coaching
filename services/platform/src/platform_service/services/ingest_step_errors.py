"""Build user-facing step failure payloads for ingestion workers."""

from __future__ import annotations

from typing import Any

from platform_service.services.ingest_user_error_messages import user_message_for_step

_MAX_DETAIL_LEN = 500


def build_step_failure(
    *,
    error_code: str,
    exc: BaseException | None = None,
    reason: str | None = None,
    stage: str | None = None,
    technical_message: str | None = None,
    error_type: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(user_message, error_jsonb)`` for ``fail_step``.

    Technical detail is stored in ``error_jsonb.detail``; ``error_message`` is
    user-facing copy from :func:`user_message_for_step`.
    """
    detail_source = technical_message
    if detail_source is None and exc is not None:
        detail_source = str(exc)
    detail = (detail_source or "")[:_MAX_DETAIL_LEN] or None

    resolved_reason = reason
    if resolved_reason is None and exc is not None:
        resolved_reason = getattr(exc, "reason", None)

    error: dict[str, Any] = {}
    if error_type is not None:
        error["type"] = error_type
    elif exc is not None:
        error["type"] = type(exc).__name__

    if resolved_reason:
        error["reason"] = resolved_reason
    if detail:
        error["detail"] = detail
    if extra:
        error.update(extra)

    user_message = user_message_for_step(
        error_code=error_code,
        error_jsonb=error,
        technical_message=detail,
        stage=stage,
    )
    return user_message, error
