"""Telemetry ingest endpoint — receives SDK event batches.

POST /telemetry/events → TelemetryAckResponse

Routing:
- `event_family == DIGITAL` → ClickHouse digital_proficiency_events.
- everything else → ClickHouse coaching_events.
- `event_type == QUIZ_ANSWERED` (legacy v3.0 scenario flow) → enqueue
  `process_gap_update_task` (sr-dev pathway, untouched).
- `event_type` ∈ MODULE_* (W-10 v3.3 module-pipeline flow) → enqueue
  `process_module_event_task` (module completion + gap state).
- `event_type` == SPICE_ACTION_OBSERVED → same task (gap observation from
  `payload_json.behavioural_gap_id`).

W-10 hardening (additive on top of the original handler):
1. Dedup by event_id via Redis SET-NX with 24h TTL — duplicates from SDK
   retries are dropped before write and reported in `duplicates`.
2. ClickHouse insert failures are caught and the rows are pushed to a
   Redis retry queue. The handler returns 202 with a `buffered` ack
   instead of 500 so the SDK doesn't keep retrying a doomed batch.
3. The ack response was widened (`duplicates`, `buffered` fields).
"""

from __future__ import annotations

import json
import logging
import time
from uuid import UUID

from fastapi import APIRouter
from mc_contracts.enums import CoachingEventType, EventFamily
from mc_contracts.telemetry import TelemetryAckResponse, TelemetryBatch, TelemetryEvent
from redis.asyncio import Redis

from platform_service.celery_tasks import process_module_event_task
from platform_service.clickhouse.client import ClickHouseClient
from platform_service.config import get_settings
from platform_service.services.telemetry_buffer import enqueue_rows
from platform_service.services.telemetry_dedup import partition_for_dedup

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
logger = logging.getLogger(__name__)

_ch_client = ClickHouseClient()
GAP_PROFILE_QUEUE = "gap_profile_update_queue"

# v3.3 module-pipeline event types (W-10). Anything in this set is routed
# to `process_module_event_task` instead of the scenario-level path.
_MODULE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        CoachingEventType.MODULE_DELIVERED.value,
        CoachingEventType.MODULE_CARD_VIEWED.value,
        CoachingEventType.MODULE_QUIZ_ATTEMPTED.value,
        CoachingEventType.MODULE_COMPLETED.value,
    }
)


def _get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def _as_ch_value(v: object) -> object:
    """Convert Enum-like values to ClickHouse-safe primitives."""
    if v is None:
        return None
    value = getattr(v, "value", None)
    return value if value is not None else v


def _event_to_row(
    *,
    e: TelemetryEvent,
    sdk_version: str,
    chw_id: int,
    tenant_id: UUID | None,
    synced_at_ms: int,
) -> list:
    """Convert TelemetryEvent to ClickHouse coaching_events column order.

    W-10 added three columns at the end (module_family_id, module_version,
    quiz_score_pct). Legacy events leave them NULL.
    """
    return [
        e.id,
        e.event_schema_version,
        sdk_version,
        e.session_id,
        e.patient_visit_id,
        e.patient_track_id,
        e.patient_id_hash,
        chw_id,
        tenant_id,
        e.village_id,
        e.upazila_id,
        e.event_family.value,
        _as_ch_value(e.event_type),
        e.module_family_id,
        e.module_id,
        e.card_family_id,
        e.quiz_family_id,
        e.module_version,
        e.quiz_score_pct,
        _as_ch_value(e.clinical_domain),
        _as_ch_value(e.card_type),
        _as_ch_value(e.trigger_type),
        _as_ch_value(e.inference_mode),
        _as_ch_value(e.outcome),
        _as_ch_value(e.validator_status),
        e.fallback_used,
        e.network_state,
        json.dumps(e.payload_json),
        e.event_date,
        e.timestamp_utc,
        e.timestamp_local,
        synced_at_ms,
    ]


def _digital_event_to_row(
    *, e: TelemetryEvent, sdk_version: str, chw_id: int, tenant_id: UUID | None
) -> list:
    """Convert TelemetryEvent to ClickHouse digital_proficiency_events column order."""
    payload = e.payload_json or {}
    # Note: legacy SDKs ship a 'sucess' typo; tolerated here for older clients.
    # Tracking ticket: replace with strict 'success' once SDK >= TBD ships.
    success = payload.get("success", payload.get("sucess"))
    error_type = payload.get("error_type", payload.get("errorType"))
    return [
        e.id,
        e.event_schema_version,
        sdk_version,
        e.session_id,
        chw_id,
        tenant_id,
        _as_ch_value(e.event_type),
        success,
        error_type,
        e.network_state,
        e.event_date,
        e.timestamp_utc,
    ]


@router.post("/events", response_model=TelemetryAckResponse)
async def ingest_events(batch: TelemetryBatch) -> TelemetryAckResponse:
    """Ingest a batch of telemetry events from the Android SDK."""
    accepted: list[str] = []
    rejected: list[str] = []
    errors: list[str] = []
    buffered: list[str] = []

    coaching_events: list[list] = []
    coaching_event_ids: list[str | None] = []
    digital_proficiency_events: list[list] = []
    digital_event_ids: list[str | None] = []
    # gap_jobs removed in the architecture reset (legacy scenario telemetry
    # path is gone); module_jobs is the only enqueue surface now.
    module_jobs: list[dict] = []

    synced_at_ms = int(time.time() * 1000)

    # ── W-10 idempotency: drop duplicates BEFORE any side-effects ──
    redis = _get_redis()
    try:
        first_seen, duplicate_ids = await partition_for_dedup(redis, batch.events)
    finally:
        await redis.aclose()

    for event in first_seen:
        try:
            if event.event_family == EventFamily.DIGITAL:
                digital_proficiency_events.append(
                    _digital_event_to_row(
                        e=event,
                        sdk_version=batch.sdk_version,
                        chw_id=batch.chw_id,
                        tenant_id=batch.tenant_id,
                    )
                )
                digital_event_ids.append(event.id)
            else:
                coaching_events.append(
                    _event_to_row(
                        e=event,
                        sdk_version=batch.sdk_version,
                        chw_id=batch.chw_id,
                        tenant_id=batch.tenant_id,
                        synced_at_ms=synced_at_ms,
                    )
                )
                coaching_event_ids.append(event.id)
            accepted.append(event.id)

            event_type_value = _as_ch_value(event.event_type)

            # W-10 module-pipeline path. The legacy v3.0 scenario-level
            # gap-update path was deleted in the architecture reset (the
            # underlying scenario / chw_gap_profile tables are gone).
            if event_type_value in _MODULE_EVENT_TYPES and event.module_id is not None:
                module_jobs.append(
                    {
                        "chw_id": batch.chw_id,
                        "tenant_id": batch.tenant_id,
                        "event_id": event.id,
                        "event_type": event_type_value,
                        "module_id": str(event.module_id),
                        "quiz_score_pct": event.quiz_score_pct,
                        "outcome": _as_ch_value(event.outcome),
                    }
                )
            elif event_type_value == CoachingEventType.SPICE_ACTION_OBSERVED.value:
                module_jobs.append(
                    {
                        "chw_id": batch.chw_id,
                        "tenant_id": batch.tenant_id,
                        "event_id": event.id,
                        "event_type": event_type_value,
                        "outcome": _as_ch_value(event.outcome),
                        "payload_json": event.payload_json or {},
                    }
                )
        except Exception as exc:
            rejected.append(event.id)
            errors.append(f"event_id={event.id}: {exc}")
            logger.warning("Telemetry event rejected event_id=%s: %s", event.id, exc)

    # ── ClickHouse writes with retry-buffer fallback (W-10) ──
    if coaching_events:
        await _insert_or_buffer(
            table="coaching_events",
            inserter=_ch_client.insert_coaching_events,
            rows=coaching_events,
            event_ids=coaching_event_ids,
            buffered_acc=buffered,
        )
    if digital_proficiency_events:
        await _insert_or_buffer(
            table="digital_events",
            inserter=_ch_client.insert_digital_proficiency_events,
            rows=digital_proficiency_events,
            event_ids=digital_event_ids,
            buffered_acc=buffered,
        )

    # Enqueue Celery jobs only for events that made it past validation. We
    # enqueue regardless of the ClickHouse outcome — the ClickHouse layer
    # is for analytics; the gap/completion state is the operational truth
    # and shouldn't be held hostage to a ClickHouse outage.
    for j in module_jobs:
        process_module_event_task.delay(j)

    return TelemetryAckResponse(
        accepted=accepted,
        rejected=rejected,
        duplicates=duplicate_ids,
        buffered=buffered,
        errors=errors,
    )


async def _insert_or_buffer(
    *,
    table: str,
    inserter,
    rows: list[list],
    event_ids: list[str | None],
    buffered_acc: list[str],
) -> None:
    """Try inserting to ClickHouse; on failure, push rows to the Redis retry
    queue and record the affected event_ids in `buffered_acc`. Never raises."""
    try:
        await inserter(rows)
        return
    except Exception:
        logger.exception(
            "ClickHouse insert failed for %d %s row(s); buffering for retry",
            len(rows),
            table,
        )
    redis = _get_redis()
    try:
        await enqueue_rows(redis, table=table, rows=rows, event_ids=event_ids)
    finally:
        await redis.aclose()
    buffered_acc.extend([eid for eid in event_ids if eid is not None])
