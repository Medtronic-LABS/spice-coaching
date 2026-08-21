"""Unit tests for path-template matching helpers."""

from __future__ import annotations

from platform_service.auth.path_template import (
    match_path_template,
    normalize_relative_path,
    path_matches_template,
)


def test_normalize_relative_path_strips_api_root() -> None:
    assert normalize_relative_path("/medtronics-api/admin/modules", "/medtronics-api") == ("/admin/modules")
    assert normalize_relative_path("/admin/modules", "") == "/admin/modules"


def test_path_matches_template_static_and_param() -> None:
    assert path_matches_template("/admin/modules/domains", "/admin/modules/domains")
    assert path_matches_template("/admin/modules/abc", "/admin/modules/{module_id}")
    assert not path_matches_template("/admin/modules/abc/extra", "/admin/modules/{module_id}")


def test_match_path_template_prefers_literal_over_param() -> None:
    templates = [
        "/admin/modules/{module_id}",
        "/admin/modules/domains",
    ]
    assert match_path_template("/admin/modules/domains", templates) == "/admin/modules/domains"
    assert match_path_template("/admin/modules/uuid-1", templates) == "/admin/modules/{module_id}"


def test_match_path_template_returns_none_when_unmatched() -> None:
    assert match_path_template("/admin/unknown", ["/admin/modules"]) is None
