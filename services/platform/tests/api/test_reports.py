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


# --- Tier B: behavioural fields read from payload_json ------------------------


def test_p_int_only_accepts_real_ints() -> None:
    assert reports._p_int({"attempt_number": 2}, "attempt_number") == 2
    assert reports._p_int({"attempt_number": True}, "attempt_number") == ""  # bool is not an int here
    assert reports._p_int({}, "attempt_number") == ""


def test_p_yn_maps_bool_to_letters() -> None:
    assert reports._p_yn({"downloaded": True}, "downloaded") == "Y"
    assert reports._p_yn({"downloaded": False}, "downloaded") == "N"
    assert reports._p_yn({}, "downloaded") == ""  # absent → blank, not N


def test_p_minutes_from_ms() -> None:
    assert reports._p_minutes({"time_spent_ms": 360000}, "time_spent_ms") == 6.0
    assert reports._p_minutes({}, "time_spent_ms") == ""


def test_p_offset_formats_m_ss() -> None:
    assert reports._p_offset({"drop_off_ms": 580000}, "drop_off_ms") == "9:40"
    assert reports._p_offset({}, "drop_off_ms") == ""


def test_p_time_trims_to_hh_mm() -> None:
    assert reports._p_time({"started_at": "2026-09-16 18:30:00"}, "started_at") == "18:30"
    assert reports._p_time({"started_at": "18:30"}, "started_at") == "18:30"
    assert reports._p_time({}, "started_at") == ""
