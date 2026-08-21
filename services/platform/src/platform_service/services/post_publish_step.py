"""Helpers for ingestion_run_step rows tied to post-publish Celery workers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from mc_contracts.errors import ErrorCode

from platform_service.db.base import SessionLocal
from platform_service.db.models.ingestion_run import IngestionRunStep
from platform_service.services.ingest_step_errors import build_step_failure
from platform_service.services.run_state_service import RunStateService


async def finish_post_publish_step(
    *,
    step_id: UUID | None,
    success: bool,
    output_summary: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    """Complete or fail a post-publish step and maybe finalize the ingestion run.

    When ``step_id`` is None (standalone enqueue without an ingestion step),
    this is a no-op.
    ``error_code``/``error_message`` are required in practice for failures —
    callers should pass an :class:`ErrorCode` value and a short technical
    message; the fallbacks below only guard against missed call sites.
    """
    if step_id is None:
        return

    async with SessionLocal() as session:
        run_state = RunStateService(session)
        if success:
            await run_state.complete_step(step_id, output_summary=output_summary)
        else:
            code = error_code or ErrorCode.GENERATION_FAILED.value
            technical = error_message
            if not technical and error:
                raw = error.get("detail") or error.get("message")
                if isinstance(raw, str):
                    technical = raw
            if not technical:
                technical = "post-publish worker failed"
            user_message, built_error = build_step_failure(
                error_code=code,
                technical_message=technical,
                error_type=error.get("type") if error else None,
                extra={k: v for k, v in (error or {}).items() if k not in {"type", "message", "detail"}}
                or None,
            )
            await run_state.fail_step(
                step_id,
                error_code=code,
                error_message=user_message,
                error=built_error,
            )
        step = await session.get(IngestionRunStep, step_id)
        if step is not None:
            await run_state.maybe_finalize_ingestion_run(step.ingestion_run_id)
        await session.commit()
