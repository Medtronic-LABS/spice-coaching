"""Unit tests for hierarchy import spreadsheet parsing."""

from __future__ import annotations

import pytest
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from platform_service.services.hierarchy_import_parser import (
    build_desired_hierarchy_from_rows,
    parse_hierarchy_import_file,
)


def test_alias_headers_and_upazila_union() -> None:
    rows = [
        [
            "division",
            "district",
            "upazila",
            "AM Name",
            "AM ID",
            "PO Name",
            "PO User Id",
            "SK Name",
            "SK User Id",
        ],
        ["Rangpur", "Lalmonirhat", "Sadar", "AM", "1", "PO", "2", "SK1", "3"],
        ["Rangpur", "Lalmonirhat", "Patgram", "AM", "1", "PO", "2", "SK2", "4"],
    ]
    desired = build_desired_hierarchy_from_rows(rows)
    assert desired.users[1].upazila_keys == {"sadar", "patgram"}
    assert desired.users[2].upazila_keys == {"sadar", "patgram"}
    assert desired.users[3].parent_id == 2
    assert desired.users[4].parent_id == 2


def test_name_conflict_rejects() -> None:
    rows = [
        [
            "Division",
            "District",
            "Upazila",
            "AM name",
            "AM mHealth Account",
            "Rural PO Name",
            "PO User_Id",
            "Sk Name",
            "SK user_id",
        ],
        ["Rangpur", "Lalmonirhat", "Sadar", "AM One", "1", "PO", "2", "SK", "3"],
        ["Rangpur", "Lalmonirhat", "Sadar", "AM Two", "1", "PO", "2", "SK", "3"],
    ]
    with pytest.raises(AppError) as exc:
        build_desired_hierarchy_from_rows(rows)
    assert exc.value.code == ErrorCode.HIERARCHY_IMPORT_INVALID.value


def test_unsupported_extension() -> None:
    with pytest.raises(AppError) as exc:
        parse_hierarchy_import_file(filename="tree.txt", data=b"x")
    assert exc.value.code == ErrorCode.HIERARCHY_IMPORT_INVALID.value
