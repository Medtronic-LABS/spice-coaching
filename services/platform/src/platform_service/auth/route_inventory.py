"""Enumerate FastAPI route path templates for catalog inventory checks."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute

from platform_service.config import Settings


def _is_exempt_relative_path(relative: str, settings: Settings) -> bool:
    """True when ``relative`` (leading slash, under api_root) is auth-exempt."""
    full = f"{settings.api_root_path_normalized}{relative}" if relative.startswith("/") else relative
    if full in settings.spice_auth_exempt_path_set:
        return True
    # Exempt suffixes are configured without requiring a leading slash match only.
    bare = relative.lstrip("/")
    for suffix in settings.spice_auth_exempt_paths.split(","):
        clean = suffix.strip().strip("/")
        if clean and bare == clean:
            return True
    return False


def enumerate_app_path_templates(app: FastAPI, settings: Settings | None = None) -> frozenset[str]:
    """Return unique path templates under ``api_root``, excluding exempt routes.

    Templates keep FastAPI ``{param}`` names and use a leading slash relative
    to ``api_root`` (e.g. ``/admin/modules/{module_id}``).
    """
    cfg = settings or Settings()
    root = cfg.api_root_path_normalized
    templates: set[str] = set()

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        if root and path.startswith(root):
            relative = path[len(root) :] or "/"
        else:
            relative = path
        if not relative.startswith("/"):
            relative = f"/{relative}"
        if relative != "/" and relative.endswith("/"):
            relative = relative.rstrip("/")
        if _is_exempt_relative_path(relative, cfg):
            continue
        templates.add(relative)

    return frozenset(templates)
