"""W-10 — module completion worker.

Consumes the v3.3 module-pipeline telemetry events
(`MODULE_DELIVERED`, `MODULE_CARD_VIEWED`, `MODULE_QUIZ_ATTEMPTED`,
`MODULE_COMPLETED`) and updates `chw_module_completion` (on
`MODULE_COMPLETED` only) plus `chw_behavioural_gap_state` for
`MODULE_QUIZ_ATTEMPTED` (via the W-8 GapStateService).

Also consumes `SPICE_ACTION_OBSERVED` (clinical workflow hook): reads
`payload_json.behavioural_gap_id` and records a gap observation via
`GapStateService.record_observation`. When `outcome` (event top-level or
`payload_json.outcome`) is `wrong` or `incorrect`, also calls
`GapStateService.record_failed_attempt` to bump `failed_attempts_count`.

Score vs `settings.quiz_pass_threshold_default` (and per-module
`pass_threshold_override` when set) only drives gap updates when `outcome`
is absent. Quiz attempts do not write `chw_module_completion`.

For `chw_behavioural_gap_state.failed_attempts_count`, `MODULE_QUIZ_ATTEMPTED`
uses the event `outcome` when present: ``incorrect`` / ``wrong`` increments
(via `record_failed_attempt`); ``correct`` decrements and sets
``status=resolved`` when the counter reaches zero (inactive for gap-based
suggestions). If `outcome` is absent or not one of those values, gap updates
fall back to the score-based pass/fail (same as before).

Learning points for `MODULE_QUIZ_ATTEMPTED` are recorded only when `outcome`
is explicitly ``correct`` (top-level or `payload_json.outcome`); score-based
gap logic is unchanged when `outcome` is absent.

Reused infrastructure:
- `GapStateService.record_failed_attempt` — already implements escalation
  when failed_attempts_count crosses `settings.quiz_failure_escalation_count`
  within `settings.quiz_failure_escalation_window_days`.
- `GapStateService.reset_after_pass` — clears failed_attempts_count and sets
  `last_reinforced_at` so periodic refresh logic stays consistent.
- `GapStateService.record_observation` — SPICE path; increments occurrence
  counters on `chw_behavioural_gap_state`.
- `GapStateService.record_failed_attempt` — SPICE path when outcome is
  incorrect; same escalation semantics as quiz failures.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import get_settings
from platform_service.db.base import SessionLocal
from platform_service.db.models.module import Module
from platform_service.db.repositories.module_completion_repository import (
    ModuleCompletionRepository,
)
from platform_service.services.gap_state_service import GapStateService
from platform_service.services.learning_points_service import LearningPointsService

logger = logging.getLogger(__name__)


# Event types this worker handles. Matches mc_contracts.enums.CoachingEventType
# but kept as plain strings here so the worker doesn't fail on legacy SDK
# payloads that pass the value as a raw string.
_HANDLED = {
    "module_delivered",
    "module_card_viewed",
    "module_quiz_attempted",
    "module_completed",
    "spice_action_observed",
}


async def process_module_event_job(payload: dict[str, Any]) -> None:
    """Apply one module-level event to platform state.

    Expected `payload` keys (forwarded from api/telemetry.py):
        chw_id: int (JSON number or numeric string)
        tenant_id: int | None
        event_type: str
        event_id: str
        Module pipeline additionally: module_id (the specific Module row the
        SDK rendered — version is encoded in this id, so no separate version
        field is needed), quiz_score_pct (0.0–1.0 on MODULE_QUIZ_ATTEMPTED;
        gap fallback only); optional outcome (correct | wrong | incorrect)
        drives gap failed_attempts_count when set. Learning points for
        MODULE_QUIZ_ATTEMPTED require outcome ``correct``. MODULE_QUIZ_ATTEMPTED does
        not write chw_module_completion (only MODULE_COMPLETED does, via
        mark_completed).
        spice_action_observed additionally: payload_json with behavioural_gap_id;
        optional outcome on the job or in payload_json (`wrong` / `incorrect`
        increment failed_attempts_count via record_failed_attempt).
    """
    event_type = (payload.get("event_type") or "").strip().lower()
    if event_type not in _HANDLED:
        logger.warning(
            "module_completion_worker received unhandled event_type=%s event_id=%s",
            event_type,
            payload.get("event_id"),
        )
        return
    if event_type in ("module_delivered", "module_card_viewed"):
        chw_id_pts = _parse_chw_id(payload.get("chw_id"))
        if chw_id_pts is None:
            logger.warning(
                "module_completion_worker dropping event_id=%s: missing chw_id for learning points",
                payload.get("event_id"),
            )
            return
        tenant_uuid_pts = _coerce_tenant_uuid(payload.get("tenant_id"))
        async with SessionLocal() as session:
            try:
                pts = LearningPointsService(session)
                await pts.try_award_from_telemetry(
                    event_id=payload.get("event_id"),
                    chw_id=chw_id_pts,
                    tenant_id=tenant_uuid_pts,
                    event_type=event_type,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "module_completion_worker failed for event_id=%s event_type=%s",
                    payload.get("event_id"),
                    event_type,
                )
                raise
        return

    if event_type == "spice_action_observed":
        raw = payload.get("payload_json")
        payload_json: dict[str, Any] = raw if isinstance(raw, dict) else {}
        chw_id_spice = _parse_chw_id(payload.get("chw_id"))
        behavioural_gap_id = _parse_uuid(
            payload_json.get("behavioural_gap_id"),
            field="behavioural_gap_id",
        )
        if chw_id_spice is None or behavioural_gap_id is None:
            logger.warning(
                "module_completion_worker dropping event_id=%s spice_action_observed: "
                "missing or invalid chw_id or payload_json.behavioural_gap_id",
                payload.get("event_id"),
            )
            return
        tenant_uuid_spice = _coerce_tenant_uuid(payload.get("tenant_id"))
        async with SessionLocal() as session:
            try:
                gap_svc = GapStateService(session)
                await gap_svc.record_observation(
                    chw_id=chw_id_spice,
                    behavioural_gap_id=behavioural_gap_id,
                    tenant_id=tenant_uuid_spice,
                    predicate=None,
                )
                if _spice_outcome_is_incorrect(payload, payload_json):
                    await gap_svc.record_failed_attempt(
                        chw_id=chw_id_spice,
                        behavioural_gap_id=behavioural_gap_id,
                        tenant_id=tenant_uuid_spice,
                    )
                pts = LearningPointsService(session)
                await pts.try_award_from_telemetry(
                    event_id=payload.get("event_id"),
                    chw_id=chw_id_spice,
                    tenant_id=tenant_uuid_spice,
                    event_type=event_type,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "module_completion_worker failed for event_id=%s event_type=%s",
                    payload.get("event_id"),
                    event_type,
                )
                raise
        return

    chw_id = _parse_chw_id(payload.get("chw_id"))
    module_id = _parse_uuid(payload.get("module_id"), field="module_id")
    if chw_id is None or module_id is None:
        logger.warning(
            "module_completion_worker dropping event_id=%s: missing chw_id or module_id",
            payload.get("event_id"),
        )
        return

    tenant_id_raw = payload.get("tenant_id")
    tenant_uuid = _coerce_tenant_uuid(tenant_id_raw)

    async with SessionLocal() as session:
        try:
            module = await session.get(Module, module_id)
            if module is None:
                logger.warning(
                    "module_completion_worker: no module row for module_id=%s event_id=%s",
                    module_id,
                    payload.get("event_id"),
                )
                return

            if event_type == "module_quiz_attempted":
                await _handle_quiz_attempt(
                    session,
                    chw_id=chw_id,
                    module=module,
                    score_pct=payload.get("quiz_score_pct"),
                    tenant_uuid=tenant_uuid,
                    event_id=payload.get("event_id"),
                    gap_outcome_kind=_module_quiz_outcome_kind(payload),
                )
            elif event_type == "module_completed":
                await _handle_module_completed(
                    session,
                    chw_id=chw_id,
                    module=module,
                )
            pts = LearningPointsService(session)
            quiz_pct = _parse_quiz_score_pct(payload.get("quiz_score_pct"))
            award_quiz_points = (
                event_type != "module_quiz_attempted" or _module_quiz_outcome_kind(payload) == "correct"
            )
            if award_quiz_points:
                await pts.try_award_from_telemetry(
                    event_id=payload.get("event_id"),
                    chw_id=chw_id,
                    tenant_id=tenant_uuid,
                    event_type=event_type,
                    quiz_score_pct=quiz_pct if event_type == "module_quiz_attempted" else None,
                )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "module_completion_worker failed for event_id=%s event_type=%s",
                payload.get("event_id"),
                event_type,
            )
            raise


# ── handlers ─────────────────────────────────────────────────────────────


async def _handle_quiz_attempt(
    session: AsyncSession,
    *,
    chw_id: int,
    module: Module,
    score_pct: float | None,
    tenant_uuid: UUID | None,
    event_id: str | None,
    gap_outcome_kind: str | None,
) -> None:
    # Mirror quiz outcome on behavioural-gap state (W-8) only when the module
    # declares a primary gap.
    if module.primary_gap_id is None:
        return

    if score_pct is None:
        logger.warning(
            "module_completion_worker: quiz_score_pct missing on event_id=%s; treating as 0.0/fail",
            event_id,
        )
        score_pct = 0.0
    score_pct = max(0.0, min(1.0, float(score_pct)))

    settings = get_settings()
    # W-11: per-module pass threshold override beats settings default.
    threshold = (
        module.pass_threshold_override
        if getattr(module, "pass_threshold_override", None) is not None
        else settings.quiz_pass_threshold_default
    )
    passed = score_pct >= threshold

    gap_svc = GapStateService(session)
    if gap_outcome_kind == "incorrect":
        await gap_svc.record_failed_attempt(
            chw_id=chw_id,
            behavioural_gap_id=module.primary_gap_id,
            tenant_id=tenant_uuid,
        )
    elif gap_outcome_kind == "correct":
        await gap_svc.record_correct_quiz_attempt(
            chw_id=chw_id,
            behavioural_gap_id=module.primary_gap_id,
        )
    elif passed:
        await gap_svc.reset_after_pass(chw_id=chw_id, behavioural_gap_id=module.primary_gap_id)
    else:
        await gap_svc.record_failed_attempt(
            chw_id=chw_id,
            behavioural_gap_id=module.primary_gap_id,
            tenant_id=tenant_uuid,
        )


async def _handle_module_completed(
    session: AsyncSession,
    *,
    chw_id: int,
    module: Module,
) -> None:
    repo = ModuleCompletionRepository(session)
    await repo.mark_completed(
        chw_id=chw_id,
        module_family_id=module.module_family_id,
        completed_module_id=module.id,
    )


# ── helpers ──────────────────────────────────────────────────────────────


def _parse_quiz_score_pct(value: object) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _parse_chw_id(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            logger.warning("module_completion_worker: invalid chw_id=%r", value)
            return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        logger.warning("module_completion_worker: invalid chw_id=%r", value)
        return None


def _parse_uuid(value: object, *, field: str) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        logger.warning("module_completion_worker: invalid UUID for %s=%r", field, value)
        return None


def _coerce_tenant_uuid(value: object) -> UUID | None:
    """tenant_id arrives as int (legacy) or str (uuid). Only forward the UUID
    flavour to chw_module_completion.tenant_id (which is UUID-typed in the
    v3.3 schema). Integer tenant ids stay legacy-only."""
    if value is None or isinstance(value, int):
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _module_quiz_outcome_kind(payload: dict[str, Any]) -> str | None:
    """How to adjust gap ``failed_attempts_count`` for MODULE_QUIZ_ATTEMPTED.

    Returns ``'correct'``, ``'incorrect'``, or ``None`` (fall back to
    score-based pass/fail for the gap). Mirrors SPICE: top-level ``outcome``
    or nested ``payload_json.outcome``.
    """
    raw = payload.get("outcome")
    if raw is None:
        nested = payload.get("payload_json")
        if isinstance(nested, dict):
            raw = nested.get("outcome")
    if raw is None:
        return None
    value = getattr(raw, "value", raw)
    normalized = str(value).strip().lower()
    if normalized == "correct":
        return "correct"
    if normalized in ("wrong", "incorrect"):
        return "incorrect"
    return None


def _spice_outcome_is_incorrect(payload: dict[str, Any], payload_json: dict[str, Any]) -> bool:
    """True when coaching outcome is a hard miss (`Outcome.WRONG` / `INCORRECT`).

    Accepts outcome on the Celery job (mirrors telemetry top-level `outcome`)
    or under `payload_json` for clients that nest it there.
    """
    raw = payload.get("outcome")
    if raw is None:
        raw = payload_json.get("outcome")
    if raw is None:
        return False
    value = getattr(raw, "value", raw)
    normalized = str(value).strip().lower()
    return normalized in ("wrong", "incorrect")
