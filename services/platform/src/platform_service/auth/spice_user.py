"""FastAPI dependency to read the authenticated SPICE user from request state."""

from __future__ import annotations

from fastapi import Request
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError

from platform_service.auth.spice_context import SpiceUserContext
from platform_service.auth.tenant_context import DEFAULT_SELECTED_TENANT_ID
from platform_service.config import get_settings


def get_spice_user(request: Request) -> SpiceUserContext:
    """Return the user context set by :class:`SpiceAuthMiddleware`."""
    user = getattr(request.state, "spice_user", None)
    if user is None:
        raise AppError(ErrorCode.NOT_AUTHENTICATED.value, "not authenticated", status=401)
    return user


def get_selected_tenant_id(request: Request) -> int:
    """Return the selected tenant set by :class:`SpiceAuthMiddleware`.

    When SPICE auth is enabled this is ``userDetail.country.tenantId`` from
    authenticate. Defaults to ``0`` if middleware did not run (auth off / exempt).
    """
    tenant_id = getattr(request.state, "selected_tenant_id", None)
    if tenant_id is None:
        return DEFAULT_SELECTED_TENANT_ID
    return int(tenant_id)


def resolve_spice_actor(request: Request) -> str:
    """Return an audit actor from the authenticated SPICE user.

    When SPICE auth is enabled, unauthenticated requests raise 401. When auth
    is disabled (local dev), fall back to ``admin``.
    """
    settings = get_settings()
    user = getattr(request.state, "spice_user", None)
    if user is None:
        if settings.spice_auth_enabled:
            raise AppError(ErrorCode.NOT_AUTHENTICATED.value, "not authenticated", status=401)
        return "admin"
    if user.username:
        return user.username
    if user.id is not None:
        return str(user.id)
    return "admin"


def resolve_optional_spice_actor(request: Request) -> str | None:
    """Return an audit actor from the SPICE user, or ``None`` when absent.

    Unlike :func:`resolve_spice_actor`, this never raises and never invents a
    synthetic ``admin`` sentinel — suitable for nullable audit columns.
    """
    user = getattr(request.state, "spice_user", None)
    if user is None:
        return None
    if user.username:
        return user.username
    if user.id is not None:
        return str(user.id)
    return None


def resolve_spice_user_id(request: Request) -> int | None:
    """Return the SPICE user id for FK-style audit columns, or ``None`` when absent."""
    user = getattr(request.state, "spice_user", None)
    if user is None or user.id is None:
        return None
    return int(user.id)
