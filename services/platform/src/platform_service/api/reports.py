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


# --- behavioural fields carried in the free-form ``payload_json`` --------------
# These keys are populated once the micro-coaching SDK emits them (LEAP-43
# Tier B). The backend stores payload_json verbatim, so no contract/migration
# change is needed — reading these keys here is all that's required. Absent →
# empty cell (never fabricated). The SDK must emit these exact key names.


def _p_int(payload: dict[str, Any], key: str) -> Any:
    v = payload.get(key)
    return int(v) if isinstance(v, int) and not isinstance(v, bool) else ""


def _p_yn(payload: dict[str, Any], key: str) -> str:
    v = payload.get(key)
    return "Y" if v is True else ("N" if v is False else "")


def _p_minutes(payload: dict[str, Any], key: str) -> Any:
    """A milliseconds value in payload → minutes (1 dp), or ''."""
    v = payload.get(key)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return ""
    return round(v / 60000, 1)


def _p_offset(payload: dict[str, Any], key: str) -> str:
    """A milliseconds offset in payload → ``M:SS`` time offset, or ''."""
    v = payload.get(key)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return ""
    total = int(v // 1000)
    return f"{total // 60}:{total % 60:02d}"


def _p_time(payload: dict[str, Any], key: str) -> str:
    """A ``HH:MM[:SS]`` / ISO time string in payload → ``HH:MM``, or ''."""
    v = payload.get(key)
    if not isinstance(v, str) or not v:
        return ""
    # Accept "HH:MM", "HH:MM:SS", or an ISO datetime → keep the HH:MM.
    return v[11:16] if len(v) >= 16 and v[10] in " T" else v[:5]


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
        select="chw_id, module_id, event_type, quiz_score_pct, outcome, session_id, "
        "timestamp_local, timestamp_utc",
    )
    module_ids = {str(r["module_id"]) for r in rows if r.get("module_id")}
    titles = await _module_titles(session, module_ids)

    # Lessons are per-event; quizzes are aggregated into one row per attempt.
    # The SDK emits per-question module_quiz_attempted events, so an "attempt" is
    # the burst of quiz events sharing (chw, module, session). rows arrive oldest
    # -first (see _events ORDER BY), so first-seen = start, last-seen = exit.
    lesson_rows: list[Sequence[Any]] = []
    attempts: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        mid = str(r["module_id"]) if r.get("module_id") else ""
        if r["event_type"] in (_LESSON_EVENT, _LESSON_DELIVERED):
            lesson_rows.append(
                [
                    r.get("chw_id"),
                    mid,
                    titles.get(mid, ""),
                    "Lesson",
                    "",
                    "",
                    _local_time(r),
                    "",
                    r.get("outcome") or "",
                ]
            )
            continue
        key = (r.get("chw_id"), mid, r.get("session_id") or "")
        a = attempts.get(key)
        if a is None:
            a = {
                "chw": r.get("chw_id"),
                "mid": mid,
                "start": _local_time(r),
                "start_utc": r.get("timestamp_utc"),
            }
            attempts[key] = a
        a["exit"] = _local_time(r)  # last event wins
        a["outcome"] = r.get("outcome") or ""
        if r.get("quiz_score_pct") is not None:
            a["score"] = r["quiz_score_pct"]

    # Attempt # = chronological rank of each attempt within its (chw, module).
    ranked: dict[tuple, int] = {}
    for key, a in sorted(
        attempts.items(), key=lambda kv: (kv[1]["chw"], kv[1]["mid"], str(kv[1]["start_utc"]))
    ):
        cm = (a["chw"], a["mid"])
        ranked[cm] = ranked.get(cm, 0) + 1
        a["attempt"] = ranked[cm]

    quiz_rows = [
        [
            a["chw"],
            a["mid"],
            titles.get(a["mid"], ""),
            "Quiz",
            round(a["score"] * 100, 1) if a.get("score") is not None else "",
            a["attempt"],
            a["start"],
            a["exit"],
            a.get("outcome", ""),
        ]
        for a in attempts.values()
    ]

    def _out() -> Iterable[Sequence[Any]]:
        yield from lesson_rows
        yield from quiz_rows

    return _csv_response(
        [
            "SK ID",
            "Lesson ID",
            "Lesson Name",
            "Activity Type",
            "Score",
            "Attempt #",
            "Start Time",
            "Exit/Drop-off Time",
            "Completion Status",
        ],
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
    doc_ids = {
        str(_payload(r).get("source_document_id")) for r in rows if _payload(r).get("source_document_id")
    }
    meta = await _document_meta(session, doc_ids)

    def _out() -> Iterable[Sequence[Any]]:
        for r in rows:
            p = _payload(r)
            doc_id = str(p.get("source_document_id") or "")
            # Only PDFs; skip non-pdf source documents when the type is known.
            info = meta.get(doc_id)
            if info and info["source_type"] and info["source_type"] != "pdf":
                continue
            # payload keys (Tier B): downloaded (bool), time_spent_ms (int).
            yield [
                doc_id,  # PDF ID
                str(r["module_id"]) if r.get("module_id") else "",  # Lesson ID
                r.get("chw_id"),  # SK ID
                "Y",  # Opened? (this IS an open event)
                _p_yn(p, "downloaded"),  # Downloaded?
                _local_dt(r),  # Timestamp
                _p_minutes(p, "time_spent_ms"),  # Time Spent (min)
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
    """Raw log — one row per video-watch session."""
    rows = await _events(
        ch,
        event_types=[_VIDEO_PROGRESS],
        from_date=from_date,
        to_date=to_date,
        tenant_id=tenant_id,
        select="chw_id, payload_json, session_id, timestamp_local, timestamp_utc",
    )

    # One row per session: the SDK emits many progress events per watch, each
    # carrying the running behavioural aggregates, so the LAST event per
    # (chw, session, video) holds the final counts. rows are oldest-first, so a
    # dict keyed on that tuple keeps the last write.
    sessions: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        p = _payload(r)
        vid = str(p.get("source_document_id") or "")
        key = (r.get("chw_id"), r.get("session_id") or "", vid)
        sessions[key] = {"chw": r.get("chw_id"), "vid": vid, "p": p, "row": r}

    def _out() -> Iterable[Sequence[Any]]:
        for s in sessions.values():
            p, r = s["p"], s["row"]
            # payload keys (Tier B): started_at, ended_at, watch_duration_ms,
            # pause_count, rewatch_count, drop_off_ms. End Time falls back to the
            # last event time.
            yield [
                s["vid"],  # Video ID
                s["chw"],  # SK ID
                _p_time(p, "started_at"),  # Start Time
                _p_time(p, "ended_at") or _local_time(r),  # End Time
                _p_minutes(p, "watch_duration_ms"),  # Total Watch Duration (min)
                _p_int(p, "pause_count"),  # Pause Count
                _p_int(p, "rewatch_count"),  # Rewatch Count
                _p_offset(p, "drop_off_ms"),  # Drop-off Point
            ]

    return _csv_response(
        [
            "Video ID",
            "SK ID",
            "Start Time",
            "End Time",
            "Total Watch Duration (min)",
            "Pause Count",
            "Rewatch Count",
            "Drop-off Point",
        ],
        _out(),
        f"microcoaching_video_usage_{from_date}_{to_date}.csv",
    )
