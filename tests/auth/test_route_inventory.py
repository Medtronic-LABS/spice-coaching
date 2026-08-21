"""Ensure the seeded api_route catalog matches FastAPI routes."""

from __future__ import annotations

from platform_service.auth.api_route_catalog import ALL_PATH_TEMPLATES
from platform_service.auth.route_inventory import enumerate_app_path_templates
from platform_service.config import Settings
from platform_service.main import create_app


def test_api_route_catalog_matches_fastapi_routes() -> None:
    settings = Settings(api_root_path="/medtronics-api", spice_auth_enabled=False)
    app = create_app()
    enumerated = enumerate_app_path_templates(app, settings=settings)
    missing_from_catalog = enumerated - ALL_PATH_TEMPLATES
    extra_in_catalog = ALL_PATH_TEMPLATES - enumerated
    assert not missing_from_catalog, f"routes missing from catalog: {sorted(missing_from_catalog)}"
    assert not extra_in_catalog, f"catalog entries with no FastAPI route: {sorted(extra_in_catalog)}"
