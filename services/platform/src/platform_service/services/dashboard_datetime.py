"""Shared timezone and datetime normalization utilities for dashboard services."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any


def to_local_datetime(value: Any) -> datetime | None:
    """Coerce value to a naive device-local wall-clock datetime.

    Preserves naive datetimes from ClickHouse timestamp_local as-is.
    If a timezone-aware datetime is provided, strips tzinfo to preserve
    the wall-clock time representation.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value
    return None


def to_utc_datetime(value: Any) -> datetime | None:
    """Coerce value to a timezone-aware UTC datetime.

    Naive datetimes are assumed to be in UTC and tagged with tzinfo=UTC.
    Timezone-aware datetimes are converted to UTC.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return None


def date_to_utc_midnight(value: Any) -> datetime | None:
    """Convert a date or datetime to UTC datetime at 00:00:00+00:00."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_utc_datetime(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    return None


def utc_range_bounds(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    """Compute inclusive UTC datetime bounds for [from_date, to_date]."""
    from_ts = datetime.combine(from_date, time.min, tzinfo=UTC)
    to_ts = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC) - timedelta(microseconds=1)
    return from_ts, to_ts


def max_datetime(*values: datetime | None) -> datetime | None:
    """Return maximum datetime across values, safely normalized to UTC."""
    present = [to_utc_datetime(v) for v in values if v is not None]
    present_non_none = [v for v in present if v is not None]
    if not present_non_none:
        return None
    return max(present_non_none)
