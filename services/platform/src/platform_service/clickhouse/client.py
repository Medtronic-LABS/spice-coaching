"""ClickHouse write client for telemetry events and LLM quality logs.

Uses clickhouse-connect (sync driver wrapped in asyncio.to_thread for
non-blocking inserts). Platform is the sole writer; dashboards read directly.

The process-scoped client is created with ``autogenerate_session_id=False`` so
concurrent ``asyncio.to_thread`` callers (e.g. parallel dashboard routes) do not
collide on a shared ClickHouse session id.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

import clickhouse_connect
from clickhouse_connect.driver.exceptions import OperationalError, ProgrammingError
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from platform_service.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Column order must match the coaching_events ClickHouse table schema.
_COACHING_EVENT_COLUMNS = [
    "id",
    "event_schema_version",
    "sdk_version",
    "session_id",
    "patient_visit_id",
    "patient_track_id",
    "patient_id_hash",
    "chw_id",
    "tenant_id",
    "village_id",
    "upazila_id",
    "event_family",
    "event_type",
    "module_family_id",
    "module_id",
    "card_family_id",
    "quiz_id",
    "module_version",
    "quiz_score_pct",
    "clinical_domain",
    "card_type",
    "trigger_type",
    "inference_mode",
    "outcome",
    "validator_status",
    "fallback_used",
    "network_state",
    "payload_json",
    "event_date",
    "timestamp_utc",
    "timestamp_local",
    "synced_at",
]

_LLM_QUALITY_COLUMNS = [
    "event_id",
    "chw_id",
    "visit_id",
    "session_id",
    "scenario_id",
    "clinical_domain",
    "llm_provider",
    "llm_model",
    "prompt_template_id",
    "prompt_template_version",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "validator_status",
    "fallback_used",
    "raw_response_text",
    "occurred_at",
]

_COACHING_OUTCOME_CORRELATION_COLUMNS = [
    "coaching_event_id",
    "patient_visit_id",
    "chw_id",
    "tenant_id",
    "village_id",
    "upazila_id",
    "scenario_id",
    "clinical_domain",
    "spice_action_type",
    "spice_action_value",
    "time_delta_seconds",
    "is_protocol_aligned",
    "outcome_source",
    "confidence_tier",
    "computed_date",
]


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transport / connection failures worth a reconnect retry."""
    if isinstance(exc, ProgrammingError):
        return False
    if isinstance(exc, (OperationalError, OSError, ConnectionError, TimeoutError, Urllib3HTTPError)):
        return True
    # Nested connection resets sometimes wrap the root cause.
    cause = exc.__cause__ or exc.__context__
    if cause is not None and cause is not exc:
        return _is_retryable(cause)
    return False


class ClickHouseClient:
    """Thin wrapper around clickhouse-connect for platform telemetry writes."""

    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            s = self._settings
            # Disable session ids so the shared process client can serve concurrent
            # queries from asyncio.to_thread without ProgrammingError collisions.
            self._client = clickhouse_connect.get_client(
                host=s.clickhouse_host,
                port=s.clickhouse_port,
                database=s.clickhouse_database,
                username=s.clickhouse_user,
                password=s.clickhouse_password,
                autogenerate_session_id=False,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _reset_client(self) -> None:
        """Drop a broken underlying connection so the next attempt reconnects."""
        self.close()

    def _run_with_retry(self, operation: str, fn: Callable[[], T]) -> T:
        max_attempts = self._settings.clickhouse_query_max_attempts
        backoff_s = self._settings.clickhouse_query_retry_backoff_ms / 1000.0
        last_exc: BaseException | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                if not _is_retryable(exc) or attempt >= max_attempts:
                    logger.exception(
                        "ClickHouse %s failed (attempt %d/%d)",
                        operation,
                        attempt,
                        max_attempts,
                    )
                    raise
                logger.warning(
                    "ClickHouse %s failed (attempt %d/%d): %s; resetting client and retrying",
                    operation,
                    attempt,
                    max_attempts,
                    exc,
                )
                self._reset_client()
                if backoff_s > 0:
                    time.sleep(backoff_s)
        assert last_exc is not None
        raise last_exc

    async def insert_coaching_events(self, rows: list[list[Any]]) -> None:
        """Insert rows into coaching_events table.

        Args:
            rows: Each row is a list of values in ``_COACHING_EVENT_COLUMNS`` order.
        """
        if not rows:
            return
        await asyncio.to_thread(self._insert_sync, "coaching_events", _COACHING_EVENT_COLUMNS, rows)

    async def insert_llm_quality_logs(self, rows: list[list[Any]]) -> None:
        """Insert rows into llm_quality_logs table."""
        if not rows:
            return
        await asyncio.to_thread(self._insert_sync, "llm_quality_logs", _LLM_QUALITY_COLUMNS, rows)

    async def insert_coaching_outcome_correlations(self, rows: list[list[Any]]) -> None:
        """Insert rows into coaching_outcome_correlation table.

        Args:
            rows: Each row is a list of values in ``_COACHING_OUTCOME_CORRELATION_COLUMNS`` order.
        """
        if not rows:
            return
        await asyncio.to_thread(
            self._insert_sync,
            "coaching_outcome_correlation",
            _COACHING_OUTCOME_CORRELATION_COLUMNS,
            rows,
        )

    def _insert_sync(self, table: str, columns: list[str], rows: list[list[Any]]) -> None:
        def _do_insert() -> None:
            client = self._get_client()
            client.insert(table, rows, column_names=columns)
            logger.debug("ClickHouse inserted %d rows into %s", len(rows), table)

        self._run_with_retry(f"insert into {table}", _do_insert)

    async def query_rows(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a ClickHouse SELECT query and return rows as dicts.

        Notes:
            - Uses clickhouse-connect sync client wrapped in `asyncio.to_thread`.
            - Intended for lightweight analytics queries (e.g., materialized views).
        """
        return await asyncio.to_thread(self._query_rows_sync, query, parameters or {})

    def _query_rows_sync(self, query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        def _do_query() -> list[dict[str, Any]]:
            client = self._get_client()
            res = client.query(query, parameters=parameters)
            cols = list(res.column_names or [])
            rows = list(res.result_rows or [])
            if not cols or not rows:
                return []
            return [dict(zip(cols, row, strict=False)) for row in rows]

        return self._run_with_retry("query", _do_query)
