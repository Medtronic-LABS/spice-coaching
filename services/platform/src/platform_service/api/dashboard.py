"""Dashboard API — ClickHouse-backed analytics for supervisors and administrators.

GET /dashboard/supervisor/{chw_id}       → SupervisorDashboardResponse
GET /dashboard/district/{upazila_id}     → DistrictDashboardResponse
GET /dashboard/llm-quality               → LLMQualityResponse

Supervisor and LLM quality routes query ClickHouse materialized views.
District dashboard still returns 501 until implemented.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from mc_contracts.dashboard import CHWSkillSnapshot, LLMQualityResponse, SupervisorDashboardResponse

from platform_service.clickhouse.client import ClickHouseClient

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)

_ch_client = ClickHouseClient()


def _not_implemented(endpoint: str) -> HTTPException:
    logger.info("Dashboard endpoint requested before implementation endpoint=%s", endpoint)
    return HTTPException(status_code=501, detail=f"{endpoint} analytics are not implemented yet.")


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@router.get("/supervisor/{chw_id}")
async def chw_dashboard(
    chw_id: int,
    period_days: int = Query(default=30, ge=1, le=366),
) -> SupervisorDashboardResponse:
    """CHW skill snapshot and gap summary (ClickHouse Tier 1)."""
    tenant_id: UUID | None = None

    base_select = """
    SELECT
      sum(cards_shown) AS cards_shown,
      sum(quiz_attempts) AS quiz_attempts,
      sum(quiz_correct) AS quiz_correct,
      (sum(quiz_correct) / nullIf(sum(quiz_attempts), 0)) AS quiz_correct_rate,
      sum(digital_help_used) AS digital_help_used
    FROM chw_daily_summary
    WHERE chw_id = {chw_id:Int64}
      AND event_date >= (today() - toIntervalDay({period_days:Int32}))
    """
    if tenant_id is None:
        query = base_select
        parameters: dict[str, Any] = {
            "chw_id": int(chw_id),
            "period_days": int(period_days),
        }
    else:
        query = base_select + "      AND tenant_id = {tenant_id:UUID}\n"
        parameters = {
            "chw_id": int(chw_id),
            "period_days": int(period_days),
            "tenant_id": tenant_id,
        }

    try:
        rows = await _ch_client.query_rows(query, parameters=parameters)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("ClickHouse query failed for supervisor dashboard")
        raise HTTPException(status_code=502, detail="Analytics backend unavailable") from None

    row: dict[str, Any] = rows[0] if rows else {}

    cards_shown = _to_int(row.get("cards_shown"), default=0)
    quiz_attempts = _to_int(row.get("quiz_attempts"), default=0)
    quiz_correct_rate = _to_float(row.get("quiz_correct_rate")) if quiz_attempts else None
    digital_help_used = _to_int(row.get("digital_help_used"), default=0)

    snapshot = CHWSkillSnapshot(
        chw_id=chw_id,
        digital_help_used=digital_help_used,
        cards_shown=cards_shown,
        cards_accepted=0,
        quiz_correct_rate=quiz_correct_rate,
        active_gaps=[],
    )

    return SupervisorDashboardResponse(
        chw_id=chw_id,
        period_days=period_days,
        chw_snapshot=snapshot,
        top_gap_scenarios=[],
        validator_failure_rate=None,
        fallback_rate=None,
    )


@router.get("/district/{upazila_id}")
async def district_dashboard(upazila_id: str, period_days: int = 30) -> None:
    """District-level rollup (ClickHouse Tier 1)."""
    raise _not_implemented("District dashboard")


@router.get("/llm-quality")
async def llm_quality(
    period_days: int = Query(default=7, ge=1, le=366),
) -> LLMQualityResponse:
    """LLM quality metrics (validator_status breakdown, fallback rate)."""
    # Stub: tenant scoping will come from auth context later.
    tenant_id: int | None = None

    query = """
    SELECT
      toInt64OrZero(sum(total_calls)) AS total_inferences,
      (sum(avg_latency_ms * total_calls) / nullIf(sum(total_calls), 0)) AS avg_latency_ms,
      (sum(failed_validation) / nullIf(sum(total_calls), 0)) AS validator_failure_rate,
      (sum(fallback_count) / nullIf(sum(total_calls), 0)) AS fallback_rate,
      (sum(total_input_tokens) / nullIf(sum(total_calls), 0)) AS avg_input_tokens,
      (sum(total_output_tokens) / nullIf(sum(total_calls), 0)) AS avg_output_tokens
    FROM llm_daily_summary
    WHERE event_date >= (today() - toIntervalDay({period_days:Int32}))
      AND ({tenant_id:Nullable(Int32)} IS NULL OR tenant_id = {tenant_id:Nullable(Int32)})
    """

    try:
        rows = await _ch_client.query_rows(
            query,
            parameters={"period_days": int(period_days), "tenant_id": tenant_id},
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("ClickHouse query failed for LLM quality dashboard")
        raise HTTPException(status_code=502, detail="Analytics backend unavailable") from None

    row: dict[str, Any] = rows[0] if rows else {}

    total_inferences = _to_int(row.get("total_inferences"), default=0)

    # If there were no calls in the selected window, ClickHouse expressions return NULLs.
    return LLMQualityResponse(
        period_days=period_days,
        total_inferences=total_inferences,
        avg_latency_ms=_to_float(row.get("avg_latency_ms")) if total_inferences else None,
        validator_failure_rate=_to_float(row.get("validator_failure_rate")) if total_inferences else None,
        fallback_rate=_to_float(row.get("fallback_rate")) if total_inferences else None,
        error_rate=None,
        avg_input_tokens=_to_float(row.get("avg_input_tokens")) if total_inferences else None,
        avg_output_tokens=_to_float(row.get("avg_output_tokens")) if total_inferences else None,
    )
