"""Unit tests for the micro-coaching report helpers (LEAP-43).

The endpoints themselves need ClickHouse + Postgres; these cover the pure
mapping/formatting helpers, which is where the report-column logic lives.
"""

from __future__ import annotations

from platform_service.api import reports


def test_payload_parses_dict() -> None:
    assert reports._payload({"payload_json": '{"source_document_id": "d-1"}'}) == {
        "source_document_id": "d-1"
    }


def test_payload_tolerates_garbage_and_empty() -> None:
    assert reports._payload({"payload_json": "not json"}) == {}
    assert reports._payload({"payload_json": ""}) == {}
    assert reports._payload({"payload_json": "[1,2]"}) == {}  # non-dict JSON
    assert reports._payload({}) == {}


def test_local_dt_trims_to_minute() -> None:
    row = {"timestamp_local": "2026-09-16 18:20:05.123"}
    assert reports._local_dt(row) == "2026-09-16 18:20"


def test_local_time_is_hh_mm() -> None:
    row = {"timestamp_local": "2026-09-16 18:41:07.000"}
    assert reports._local_time(row) == "18:41"


def test_time_helpers_fall_back_to_utc_then_blank() -> None:
    assert reports._local_dt({"timestamp_utc": "2026-09-16 10:02:00"}) == "2026-09-16 10:02"
    assert reports._local_time({}) == ""
    assert reports._local_dt({}) == ""
