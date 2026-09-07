"""Human-readable error enrichment for partially-succeeded ingest runs/batches."""

from __future__ import annotations

from typing import Any

from mc_contracts.errors import ErrorCode

from platform_service.db.models.ingestion_run import IngestionRunStep
from platform_service.services.ingest_user_error_messages import user_message_for_step
from platform_service.services.run_state.constants import (
    _PIPELINE_CLAIM_KEY,
    BATCH_PARTIALLY_SUCCEEDED,
    POST_PUBLISH_STAGES,
    RUN_PARTIALLY_SUCCEEDED,
    STAGE_CANDIDATE_MERGE,
    STAGE_CARD_DRAFT,
    STAGE_EXTRACT,
    STAGE_GAP_CLASSIFICATION,
    STAGE_MODULE_IDENTIFY,
    STAGE_QUIZ_GENERATION,
    STAGE_THUMBNAIL,
    STAGE_TRIGGER_BINDING,
    STEP_FAILED,
    as_error_object,
)

# Mirror ingest_progress_catalog titles so this module does not import the catalog
# (which would create a constants ↔ summarizer ↔ catalog cycle).
_STAGE_TITLES: dict[str, str] = {
    STAGE_THUMBNAIL: "Generating thumbnail",
    STAGE_EXTRACT: "Extracting content",
    STAGE_MODULE_IDENTIFY: "Identifying modules",
    STAGE_CARD_DRAFT: "Drafting module cards",
    STAGE_QUIZ_GENERATION: "Generating quiz",
    STAGE_GAP_CLASSIFICATION: "Classifying behavioural gaps",
    STAGE_TRIGGER_BINDING: "Binding triggers",
    STAGE_CANDIDATE_MERGE: "Merging module candidates",
}

_IDENTIFY_NO_CANDIDATES_MESSAGE = "Module identify stage completed without emitting any candidates."

_MAX_CAUSES = 5


def _stage_title(stage: str) -> str:
    if stage in _STAGE_TITLES:
        return _STAGE_TITLES[stage]
    return stage.replace("_", " ").strip().capitalize() or stage


def _message_from_error_fields(error: dict[str, Any]) -> str | None:
    """Derive a human-readable message from structural error fields only."""
    existing = error.get("message")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()

    code = error.get("code")
    if code == ErrorCode.IDENTIFY_NO_CANDIDATES.value:
        return _IDENTIFY_NO_CANDIDATES_MESSAGE

    draft_failures = error.get("draft_failures")
    if draft_failures is not None:
        try:
            failures = int(draft_failures)
        except (TypeError, ValueError):
            failures = 0
        try:
            produced = int(error.get("drafts_produced") or 0)
        except (TypeError, ValueError):
            produced = 0
        total = failures + produced
        if total > 0:
            return (
                f"Card drafting failed for {failures} of {total} module candidate(s); "
                f"{produced} module(s) were still produced."
            )
        return f"Card drafting failed for {failures} module candidate(s)."

    failed_stages = error.get("failed_stages")
    if isinstance(failed_stages, list) and failed_stages:
        post_publish = [s for s in failed_stages if s in POST_PUBLISH_STAGES]
        if post_publish and not error.get("draft_failures"):
            # Prefer unique titles in encounter order.
            titles: list[str] = []
            seen: set[str] = set()
            for stage in post_publish:
                title = _stage_title(str(stage))
                if title not in seen:
                    seen.add(title)
                    titles.append(title)
            return f"Post-publish step(s) failed: {', '.join(titles)}."
        if len(failed_stages) == 1:
            return f"{_stage_title(str(failed_stages[0]))} failed."
        titles = [_stage_title(str(s)) for s in failed_stages]
        return f"Pipeline step(s) failed: {', '.join(titles)}."

    failed_stage = error.get("failed_stage")
    if isinstance(failed_stage, str) and failed_stage:
        return f"{_stage_title(failed_stage)} failed."

    detail = error.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()

    return None


def _step_user_message(step: IngestionRunStep) -> str | None:
    technical = step.error_message
    if not technical:
        err = as_error_object(step.error_jsonb)
        raw = err.get("detail") or err.get("message")
        if isinstance(raw, str):
            technical = raw
    if not technical and not step.error_jsonb and not step.error_code:
        return None
    return user_message_for_step(
        error_code=step.error_code,
        error_jsonb=step.error_jsonb,
        technical_message=technical,
        stage=step.stage,
    )


def _message_from_failed_steps(steps: list[IngestionRunStep]) -> str | None:
    """Prefer the first failed step's user-facing error message."""
    for step in steps:
        if step.status != STEP_FAILED:
            continue
        if step.stage == STAGE_THUMBNAIL:
            continue
        message = _step_user_message(step)
        if message:
            return message
    return None


def _causes_from_steps(steps: list[IngestionRunStep]) -> list[dict[str, Any]]:
    causes: list[dict[str, Any]] = []
    for step in steps:
        if step.status != STEP_FAILED:
            continue
        if step.stage == STAGE_THUMBNAIL:
            continue
        cause: dict[str, Any] = {"stage": step.stage}
        if step.error_code:
            cause["code"] = step.error_code
        message = _step_user_message(step)
        if message:
            cause["message"] = message
        detail = as_error_object(step.error_jsonb).get("detail")
        if isinstance(detail, str) and detail.strip():
            cause["detail"] = detail.strip()
        causes.append(cause)
        if len(causes) >= _MAX_CAUSES:
            break
    return causes


def summarize_ingestion_run_error(
    error_jsonb: dict[str, Any] | None,
    *,
    steps: list[IngestionRunStep] | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    """Enrich run ``error_jsonb`` with ``message`` (and optional ``causes``).

    Strips internal pipeline-claim keys. Returns ``None`` when there is nothing
    to present after stripping. When ``status`` is not partial/failed and the
    payload has no structural failure fields, still returns cleaned error if
    non-empty (e.g. leftover run metadata).
    """
    error = dict(as_error_object(error_jsonb))
    error.pop(_PIPELINE_CLAIM_KEY, None)
    if not error and not steps:
        return None

    if status in (RUN_PARTIALLY_SUCCEEDED, None) or error:
        message = None
        if isinstance(error.get("message"), str) and error["message"].strip():
            message = user_message_for_step(
                error_code=error.get("code") if isinstance(error.get("code"), str) else None,
                error_jsonb=error,
                technical_message=error["message"].strip(),
            )
        elif steps:
            message = _message_from_failed_steps(steps)
        if message is None:
            message = _message_from_error_fields(error)
        if message:
            error["message"] = message

    if steps:
        causes = _causes_from_steps(steps)
        if causes:
            error["causes"] = causes

    return error or None


def summarize_error_from_failed_children(
    child_nodes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build a compact error for a rolled-up ``partially_succeeded`` tree node."""
    causes: list[dict[str, Any]] = []
    messages: list[str] = []

    def _walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if str(node.get("status")) == STEP_FAILED:
                cause: dict[str, Any] = {"stage": node.get("key") or "step"}
                code = node.get("error_code")
                if code:
                    cause["code"] = code
                msg = node.get("error_message")
                err = node.get("error")
                detail = None
                if isinstance(err, dict):
                    raw_detail = err.get("detail")
                    if isinstance(raw_detail, str) and raw_detail.strip():
                        detail = raw_detail.strip()
                if not msg and isinstance(err, dict):
                    raw = err.get("detail") or err.get("message")
                    if isinstance(raw, str) and raw.strip():
                        msg = raw.strip()
                    if not code and err.get("code"):
                        cause["code"] = err["code"]
                    if err.get("type") and "type" not in cause:
                        cause["type"] = err["type"]
                if isinstance(msg, str) and msg.strip():
                    friendly = user_message_for_step(
                        error_code=code if isinstance(code, str) else None,
                        error_jsonb=err if isinstance(err, dict) else None,
                        technical_message=msg.strip(),
                        stage=str(node.get("key") or "step"),
                    )
                    cause["message"] = friendly
                    messages.append(friendly)
                if detail:
                    cause["detail"] = detail
                causes.append(cause)
                if len(causes) >= _MAX_CAUSES:
                    return
            children = node.get("children")
            if isinstance(children, list) and children:
                _walk(children)
                if len(causes) >= _MAX_CAUSES:
                    return

    _walk(child_nodes)
    if not causes and not messages:
        return {
            "message": "One or more nested pipeline steps failed.",
        }
    out: dict[str, Any] = {}
    if messages:
        out["message"] = messages[0]
    elif causes:
        stage = str(causes[0].get("stage") or "step")
        out["message"] = f"{_stage_title(stage)} failed."
    if causes:
        out["causes"] = causes
    return out


def summarize_batch_error(
    batch_status: str,
    source_errors: list[dict[str, Any] | None],
    *,
    document_labels: list[str] | None = None,
) -> dict[str, Any] | None:
    """Aggregate per-source errors into a batch-level ``error`` for poll responses."""
    if batch_status != BATCH_PARTIALLY_SUCCEEDED:
        return None

    total = len(source_errors)
    with_error = [e for e in source_errors if e]
    n_partial = len(with_error)
    if total == 0:
        return {"message": "Batch partially succeeded."}

    message = f"{n_partial} of {total} sources partially succeeded."
    causes: list[dict[str, Any]] = []
    for idx, err in enumerate(source_errors):
        if not err:
            continue
        cause: dict[str, Any] = {"document_index": idx}
        if document_labels is not None and idx < len(document_labels):
            label = document_labels[idx]
            if label:
                cause["document_label"] = label
        msg = err.get("message")
        if isinstance(msg, str) and msg.strip():
            cause["message"] = msg.strip()
        code = err.get("code")
        if code:
            cause["code"] = code
        causes.append(cause)
        if len(causes) >= _MAX_CAUSES:
            break

    out: dict[str, Any] = {"message": message}
    if causes:
        out["causes"] = causes
    return out
