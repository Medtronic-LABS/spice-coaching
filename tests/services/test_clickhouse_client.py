"""Unit tests for ClickHouseClient retry / reconnect and concurrent query safety."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from clickhouse_connect.driver.exceptions import OperationalError, ProgrammingError
from platform_service.clickhouse.client import ClickHouseClient, _is_retryable


def _settings(*, max_attempts: int = 3, backoff_ms: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        clickhouse_host="localhost",
        clickhouse_port=8123,
        clickhouse_database="default",
        clickhouse_user="default",
        clickhouse_password="",
        clickhouse_query_max_attempts=max_attempts,
        clickhouse_query_retry_backoff_ms=backoff_ms,
    )


def _client_with_settings(**kwargs: int) -> ClickHouseClient:
    with patch(
        "platform_service.clickhouse.client.get_settings",
        return_value=_settings(**kwargs),
    ):
        return ClickHouseClient()


def test_is_retryable_classifies_transport_errors() -> None:
    assert _is_retryable(OperationalError("boom")) is True
    assert _is_retryable(ConnectionResetError("reset")) is True
    assert _is_retryable(TimeoutError("timeout")) is True
    assert _is_retryable(ProgrammingError("bad sql")) is False
    assert _is_retryable(ValueError("nope")) is False


def test_get_client_disables_session_id() -> None:
    ch = _client_with_settings()
    fake = MagicMock()
    with patch(
        "platform_service.clickhouse.client.clickhouse_connect.get_client",
        return_value=fake,
    ) as get_client:
        assert ch._get_client() is fake
        get_client.assert_called_once()
        assert get_client.call_args.kwargs["autogenerate_session_id"] is False


def test_query_rows_retries_transient_then_succeeds() -> None:
    ch = _client_with_settings(max_attempts=3, backoff_ms=0)
    ok = MagicMock()
    ok.column_names = ["n"]
    ok.result_rows = [(1,)]
    broken = MagicMock()
    broken.query.side_effect = OperationalError("connection reset")
    good = MagicMock()
    good.query.return_value = ok

    clients = iter([broken, good])

    def _get_client_side_effect(**_kwargs: object) -> MagicMock:
        return next(clients)

    with patch(
        "platform_service.clickhouse.client.clickhouse_connect.get_client",
        side_effect=_get_client_side_effect,
    ) as get_client:
        rows = ch._query_rows_sync("SELECT 1", {})
        assert rows == [{"n": 1}]
        assert get_client.call_count == 2
        broken.close.assert_called_once()


def test_query_rows_exhausted_retries_raise() -> None:
    ch = _client_with_settings(max_attempts=2, backoff_ms=0)
    broken = MagicMock()
    broken.query.side_effect = OperationalError("down")

    with patch(
        "platform_service.clickhouse.client.clickhouse_connect.get_client",
        return_value=broken,
    ):
        with pytest.raises(OperationalError, match="down"):
            ch._query_rows_sync("SELECT 1", {})
        assert broken.query.call_count == 2


def test_query_rows_does_not_retry_programming_error() -> None:
    ch = _client_with_settings(max_attempts=3, backoff_ms=0)
    client = MagicMock()
    client.query.side_effect = ProgrammingError("syntax")

    with patch(
        "platform_service.clickhouse.client.clickhouse_connect.get_client",
        return_value=client,
    ):
        with pytest.raises(ProgrammingError, match="syntax"):
            ch._query_rows_sync("SELECT bad", {})
        assert client.query.call_count == 1


def test_insert_sync_retries_transient_then_succeeds() -> None:
    ch = _client_with_settings(max_attempts=3, backoff_ms=0)
    broken = MagicMock()
    broken.insert.side_effect = OperationalError("blip")
    good = MagicMock()
    clients = iter([broken, good])

    with patch(
        "platform_service.clickhouse.client.clickhouse_connect.get_client",
        side_effect=lambda **_k: next(clients),
    ):
        ch._insert_sync("coaching_events", ["id"], [[1]])
        good.insert.assert_called_once()
        broken.close.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_query_rows_share_client_without_session() -> None:
    """Parallel dashboard-style calls must all succeed on one shared client."""
    ch = _client_with_settings()
    underlying = MagicMock()

    def _query(_sql: str, parameters: dict | None = None) -> MagicMock:
        del parameters
        result = MagicMock()
        result.column_names = ["v"]
        result.result_rows = [(1,)]
        return result

    underlying.query.side_effect = _query

    with patch(
        "platform_service.clickhouse.client.clickhouse_connect.get_client",
        return_value=underlying,
    ) as get_client:
        results = await asyncio.gather(
            ch.query_rows("SELECT 1"),
            ch.query_rows("SELECT 2"),
            ch.query_rows("SELECT 3"),
            ch.query_rows("SELECT 4"),
        )
        assert results == [[{"v": 1}]] * 4
        assert get_client.call_count == 1
        assert get_client.call_args.kwargs["autogenerate_session_id"] is False
        assert underlying.query.call_count == 4
