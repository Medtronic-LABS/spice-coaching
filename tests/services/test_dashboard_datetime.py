"""Unit tests for dashboard timezone and datetime normalization utilities."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from platform_service.services.dashboard_datetime import (
    date_to_utc_midnight,
    max_datetime,
    to_local_datetime,
    to_utc_datetime,
    utc_range_bounds,
)


def test_to_local_datetime_none() -> None:
    assert to_local_datetime(None) is None
    assert to_local_datetime("not-a-datetime") is None


def test_to_local_datetime_preserves_naive() -> None:
    dt = datetime(2026, 8, 25, 18, 30, 0)
    res = to_local_datetime(dt)
    assert res is not None
    assert res.tzinfo is None
    assert res == datetime(2026, 8, 25, 18, 30, 0)


def test_to_local_datetime_strips_aware() -> None:
    tz_plus_6 = timezone(timedelta(hours=6))
    dt = datetime(2026, 8, 25, 18, 30, 0, tzinfo=tz_plus_6)
    res = to_local_datetime(dt)
    assert res is not None
    assert res.tzinfo is None
    assert res == datetime(2026, 8, 25, 18, 30, 0)


def test_to_utc_datetime_none() -> None:
    assert to_utc_datetime(None) is None
    assert to_utc_datetime("not-a-datetime") is None


def test_to_utc_datetime_naive() -> None:
    dt = datetime(2026, 8, 25, 12, 30, 0)
    res = to_utc_datetime(dt)
    assert res is not None
    assert res.tzinfo == UTC
    assert res.year == 2026
    assert res.month == 8
    assert res.day == 25
    assert res.hour == 12
    assert res.minute == 30


def test_to_utc_datetime_aware() -> None:
    tz_plus_6 = timezone(timedelta(hours=6))
    dt = datetime(2026, 8, 25, 18, 30, 0, tzinfo=tz_plus_6)
    res = to_utc_datetime(dt)
    assert res is not None
    assert res.tzinfo == UTC
    assert res.hour == 12
    assert res.minute == 30


def test_date_to_utc_midnight() -> None:
    assert date_to_utc_midnight(None) is None
    d = date(2026, 8, 25)
    res = date_to_utc_midnight(d)
    assert res == datetime(2026, 8, 25, 0, 0, 0, tzinfo=UTC)

    dt = datetime(2026, 8, 25, 14, 0, 0)
    res_dt = date_to_utc_midnight(dt)
    assert res_dt == datetime(2026, 8, 25, 14, 0, 0, tzinfo=UTC)


def test_utc_range_bounds() -> None:
    from_date = date(2026, 4, 1)
    to_date = date(2026, 4, 30)
    from_ts, to_ts = utc_range_bounds(from_date, to_date)
    assert from_ts == datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)
    assert to_ts == datetime(2026, 4, 30, 23, 59, 59, 999999, tzinfo=UTC)


def test_max_datetime_safe_comparisons() -> None:
    assert max_datetime() is None
    assert max_datetime(None, None) is None

    naive = datetime(2026, 8, 25, 10, 0, 0)
    aware_early = datetime(2026, 8, 25, 8, 0, 0, tzinfo=UTC)
    aware_late = datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC)

    # Comparing naive and aware should not raise TypeError
    res = max_datetime(naive, aware_early)
    assert res == datetime(2026, 8, 25, 10, 0, 0, tzinfo=UTC)

    res2 = max_datetime(naive, aware_late, None)
    assert res2 == datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC)
