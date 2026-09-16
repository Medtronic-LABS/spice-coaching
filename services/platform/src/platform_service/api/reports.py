"""Micro-coaching usage reports — raw data logs as CSV (LEAP-43).

Three raw-data-log exports, one row per record, for downstream aggregation:

* ``/reports/microcoaching/lessons.csv``   — lesson & quiz activity
* ``/reports/microcoaching/pdf-usage.csv`` — PDF-open events
* ``/reports/microcoaching/video-usage.csv`` — video-watch sessions

All three read the raw event stream in ClickHouse (``coaching_events``) and
enrich ids with names from Postgres (module titles, source-document titles).

Scope note: these are raw operational exports. Filtering is by date range and
an optional ``tenant_id`` (the ClickHouse tenant UUID). Behind Spice auth this
router should be restricted to an admin/analyst role before it is exposed
outside a trusted network — left open here to match the dev ``SPICE_AUTH_ENABLED
= false`` posture; wire a scope dependency when enabling auth.

Fields the micro-coaching SDK does not yet emit are rendered as an empty cell
(never a fabricated value): quiz attempt number, activity start/exit-drop-off
time, PDF downloaded?/time-spent, and video start/end/pause-count/rewatch-count/
drop-off point. Capturing those needs an SDK + telemetry-contract change
(tracked as the second tier of LEAP-43); the identity/score/timestamp columns
below are complete today.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator, Iterable, Sequence
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from platform_service.deps import get_clickhouse_client, get_db

router = APIRouter(prefix="/reports", tags=["reports"])

# Event types that make up one row of each log (values from
# mc_contracts.enums.CoachingEventType).
_LESSON_EVENT = "module_card_viewed"
_LESSON_DELIVERED = "module_delivered"
_QUIZ_ATTEMPT_EVENT = "module_quiz_attempted"
_QUIZ_VIEW_EVENT = "module_quiz_viewed"
_DOCUMENT_VIEWED = "document_viewed"
_VIDEO_PROGRESS = "video_progress_updated"


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    """Parse the ``payload_json`` string column into a dict (empty on garbage)."""
    raw = row.get("payload_json")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def _local_dt(row: dict[str, Any]) -> str:
    """``timestamp_local`` as ``YYYY-MM-DD HH:MM`` (sheet format), or ''."""
    ts = row.get("timestamp_local") or row.get("timestamp_utc")
    if ts is None:
        return ""
    return str(ts)[:16]  # DateTime64 -> "2026-08-14 18:20:...", trim to minute


def _local_time(row: dict[str, Any]) -> str:
    """``timestamp_local`` as ``HH:MM`` time-of-day, or ''."""
    ts = row.get("timestamp_local") or row.get("timestamp_utc")
    if ts is None:
        return ""
    return str(ts)[11:16]


def _csv_response(header: Sequence[str], rows: Iterable[Sequence[Any]], filename: str) -> Response:
    """Stream the rows as a downloadable CSV."""

    async def _body() -> AsyncIterator[bytes]:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(header)
        yield buf.getvalue().encode("utf-8")
        for row in rows:
            buf.seek(0)
            buf.truncate(0)
            writer.writerow(["" if v is None else v for v in row])
            yield buf.getvalue().encode("utf-8")

    return StreamingResponse(
        _body(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _events(
    ch: Any,
    *,
    event_types: Sequence[str],
    from_date: date,
    to_date: date,
    tenant_id: str | None,
    select: str,
) -> list[dict[str, Any]]:
    """Fetch coaching_events rows of the given types in the date range."""
    params: dict[str, Any] = {
        "types": list(event_types),
        "from_date": from_date,
        "to_date": to_date,
    }
    where = "event_type IN {types:Array(String)} AND event_date >= {from_date:Date} AND event_date <= {to_date:Date}"
    if tenant_id:
        where += " AND tenant_id = {tenant_id:UUID}"
        params["tenant_id"] = tenant_id
    query = f"SELECT {select} FROM coaching_events WHERE {where} ORDER BY timestamp_utc"
    return await ch.query_rows(query, params)


async def _module_titles(session: AsyncSession, module_ids: set[str]) -> dict[str, str]:
    """{module_id: english title} for the given module ids (best-effort)."""
    if not module_ids:
        return {}
    result = await session.execute(
        text(
            "SELECT id::text AS id, "
            "COALESCE(title_localized->>'en', title_localized->>'bn', '') AS title "
            "FROM module WHERE id = ANY(:ids)"
        ),
        {"ids": list(module_ids)},
    )
    return {r.id: r.title for r in result}


async def _document_meta(session: AsyncSession, doc_ids: set[str]) -> dict[str, dict[str, str]]:
    """{source_document_id: {title, source_type}} (best-effort)."""
    if not doc_ids:
        return {}
    result = await session.execute(
        text(
            "SELECT id::text AS id, COALESCE(title, '') AS title, "
            "source_type FROM source_document WHERE id = ANY(:ids)"
        ),
        {"ids": list(doc_ids)},
    )
    return {r.id: {"title": r.title, "source_type": r.source_type} for r in result}


_FromDate = Query(..., description="UTC start date (inclusive), YYYY-MM-DD.")
_ToDate = Query(..., description="UTC end date (inclusive), YYYY-MM-DD.")
_Tenant = Query(default=None, description="Optional ClickHouse tenant UUID filter.")


@router.get("/microcoaching/lessons.csv")
async def lessons_report(
    from_date: date = _FromDate,
    to_date: date = _ToDate,
    tenant_id: str | None = _Tenant,
    ch: Any = Depends(get_clickhouse_client),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Raw log — one row per lesson/quiz activity per SK."""
    rows = await _events(
        ch,
        event_types=[_LESSON_EVENT, _LESSON_DELIVERED, _QUIZ_VIEW_EVENT, _QUIZ_ATTEMPT_EVENT],
        from_date=from_date,
        to_date=to_date,
        tenant_id=tenant_id,
        select="chw_id, module_id, event_type, quiz_score_pct, outcome, timestamp_local, timestamp_utc",
    )
    module_ids = {str(r["module_id"]) for r in rows if r.get("module_id")}
    titles = await _module_titles(session, module_ids)

    def _out() -> Iterable[Sequence[Any]]:
        for r in rows:
            is_quiz = r["event_type"] in (_QUIZ_ATTEMPT_EVENT, _QUIZ_VIEW_EVENT)
            mid = str(r["module_id"]) if r.get("module_id") else ""
            score = r.get("quiz_score_pct")
            yield [
                r.get("chw_id"),                       # SK ID
                mid,                                   # Lesson ID
                titles.get(mid, ""),                   # Lesson Name
                "Quiz" if is_quiz else "Lesson",       # Activity Type
                round(score * 100, 1) if is_quiz and score is not None else "",  # Score
                "",                                    # Attempt # (SDK does not emit)
                _local_time(r),                        # Start Time
                "",                                    # Exit/Drop-off Time (SDK does not emit)
                r.get("outcome") or "",                # Completion Status
            ]

    return _csv_response(
        ["SK ID", "Lesson ID", "Lesson Name", "Activity Type", "Score",
         "Attempt #", "Start Time", "Exit/Drop-off Time", "Completion Status"],
        _out(),
        f"microcoaching_lessons_{from_date}_{to_date}.csv",
    )


@router.get("/microcoaching/pdf-usage.csv")
async def pdf_usage_report(
    from_date: date = _FromDate,
    to_date: date = _ToDate,
    tenant_id: str | None = _Tenant,
    ch: Any = Depends(get_clickhouse_client),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Raw log — one row per PDF-open event."""
    rows = await _events(
        ch,
        event_types=[_DOCUMENT_VIEWED],
        from_date=from_date,
        to_date=to_date,
        tenant_id=tenant_id,
        select="chw_id, module_id, payload_json, timestamp_local, timestamp_utc",
    )
    doc_ids = {str(_payload(r).get("source_document_id")) for r in rows if _payload(r).get("source_document_id")}
    meta = await _document_meta(session, doc_ids)

    def _out() -> Iterable[Sequence[Any]]:
        for r in rows:
            p = _payload(r)
            doc_id = str(p.get("source_document_id") or "")
            # Only PDFs; skip non-pdf source documents when the type is known.
            info = meta.get(doc_id)
            if info and info["source_type"] and info["source_type"] != "pdf":
                continue
            yield [
                doc_id,                                # PDF ID
                str(r["module_id"]) if r.get("module_id") else "",  # Lesson ID
                r.get("chw_id"),                       # SK ID
                "Y",                                   # Opened? (this IS an open event)
                "",                                    # Downloaded? (SDK does not emit)
                _local_dt(r),                          # Timestamp
                "",                                    # Time Spent (min) (SDK does not emit)
            ]

    return _csv_response(
        ["PDF ID", "Lesson ID", "SK ID", "Opened?", "Downloaded?", "Timestamp", "Time Spent (min)"],
        _out(),
        f"microcoaching_pdf_usage_{from_date}_{to_date}.csv",
    )


@router.get("/microcoaching/video-usage.csv")
async def video_usage_report(
    from_date: date = _FromDate,
    to_date: date = _ToDate,
    tenant_id: str | None = _Tenant,
    ch: Any = Depends(get_clickhouse_client),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Raw log — one row per video-progress event."""
    rows = await _events(
        ch,
        event_types=[_VIDEO_PROGRESS],
        from_date=from_date,
        to_date=to_date,
        tenant_id=tenant_id,
        select="chw_id, payload_json, timestamp_local, timestamp_utc",
    )

    def _out() -> Iterable[Sequence[Any]]:
        for r in rows:
            p = _payload(r)
            yield [
                str(p.get("source_document_id") or ""),  # Video ID
                r.get("chw_id"),                          # SK ID
                "",                                       # Start Time (SDK does not emit)
                _local_time(r),                           # End Time (progress event time)
                "",                                       # Total Watch Duration (min) (SDK does not emit)
                "",                                       # Pause Count (SDK does not emit)
                "",                                       # Rewatch Count (SDK does not emit)
                "",                                       # Drop-off Point (SDK does not emit)
            ]

    return _csv_response(
        ["Video ID", "SK ID", "Start Time", "End Time", "Total Watch Duration (min)",
         "Pause Count", "Rewatch Count", "Drop-off Point"],
        _out(),
        f"microcoaching_video_usage_{from_date}_{to_date}.csv",
    )
