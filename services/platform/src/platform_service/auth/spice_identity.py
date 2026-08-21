"""Bind request-scoped CHW identity to the authenticated SPICE principal."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from mc_contracts.enums import HierarchyRole
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_context import SpiceUserContext
from platform_service.auth.spice_principal import (
    is_admin_principal,
    is_device_principal,
    is_organizer_principal,
)
from platform_service.auth.spice_user import get_selected_tenant_id
from platform_service.config import get_settings
from platform_service.services.dashboard_hierarchy import org_user_index


def _spice_user(request: Request) -> SpiceUserContext | None:
    return getattr(request.state, "spice_user", None)


def _require_spice_user(request: Request) -> SpiceUserContext:
    user = _spice_user(request)
    if user is None:
        raise AppError(ErrorCode.NOT_AUTHENTICATED.value, "not authenticated", status=401)
    return user


def resolve_chw_id_for_device_route(
    request: Request,
    requested_chw_id: int | None,
) -> int | None:
    """Return the CHW id for a device-plane route.

    When SPICE auth is enabled, device principals may only act as their own
    ``user.id``. Admin principals may pass an explicit ``requested_chw_id``.
    When auth is disabled, ``requested_chw_id`` is returned unchanged.
    """
    settings = get_settings()
    if not settings.spice_auth_enabled:
        return requested_chw_id

    # Ensure user is authenticated
    user = _require_spice_user(request)
    if user.id is None:
        raise AppError(ErrorCode.FORBIDDEN.value, "authenticated user has no id", status=403)

    if is_admin_principal(user) and requested_chw_id is not None:
        return requested_chw_id

    if requested_chw_id is not None and requested_chw_id != user.id:
        raise AppError(
            ErrorCode.FORBIDDEN.value,
            f"chw_id {requested_chw_id} does not match authenticated user",
            status=403,
        )
    return user.id


def require_chw_id_for_device_route(request: Request, requested_chw_id: int) -> int:
    """Like :func:`resolve_chw_id_for_device_route` but always returns an int."""
    resolved = resolve_chw_id_for_device_route(request, requested_chw_id)
    if resolved is None:
        raise AppError(ErrorCode.CHW_ID_REQUIRED.value, "chw_id is required", status=400)
    return resolved


SYNC_AUTH_DISABLED_DEFAULT_USER_ID = 17


def resolve_sync_user_id(request: Request) -> int:
    """Return the CHW/user id for ``GET /sync/*`` routes that scope data to the caller.

    When SPICE auth is disabled, returns :data:`SYNC_AUTH_DISABLED_DEFAULT_USER_ID`.
    When auth is enabled, returns the authenticated principal's ``user.id`` (no query override).
    """
    if not get_settings().spice_auth_enabled:
        return SYNC_AUTH_DISABLED_DEFAULT_USER_ID

    user = _require_spice_user(request)
    if user.id is None:
        raise AppError(ErrorCode.FORBIDDEN.value, "authenticated user has no id", status=403)
    return user.id


def require_chw_id_for_telemetry(request: Request, batch_chw_id: int) -> int:
    """Enforce that telemetry batch ``chw_id`` matches the authenticated device user."""
    settings = get_settings()
    if not settings.spice_auth_enabled:
        return batch_chw_id

    user = _require_spice_user(request)
    if user.id is None:
        raise AppError(ErrorCode.FORBIDDEN.value, "authenticated user has no id", status=403)

    if is_device_principal(user) and batch_chw_id != user.id:
        raise AppError(
            ErrorCode.FORBIDDEN.value,
            f"batch chw_id {batch_chw_id} does not match authenticated user",
            status=403,
        )
    return batch_chw_id


def resolve_tenant_id_for_device_route(
    request: Request,
    requested_tenant_id: int | None = None,
) -> int:
    """Return the selected tenant int for a device-plane route.

    Selected tenant comes from authenticate ``userDetail.country.tenantId``
    (middleware). Body/query ``requested_tenant_id`` and request ``TenantId``
    are ignored for selection.
    """
    _ = requested_tenant_id
    return get_selected_tenant_id(request)


def resolve_tenant_id_for_admin(
    request: Request,
    requested_tenant_id: int | None = None,
) -> int:
    """Resolve tenant scope for admin-plane routes (modules, ingest)."""
    return resolve_tenant_id_for_dashboard(request, requested_tenant_id)


@dataclass(frozen=True, slots=True)
class TeamActivityScope:
    """Caller gate for ``GET /dashboard/team-activity``.

    Focus/level resolution happens in the service via hierarchy helpers.
    ``unrestricted`` (admin / auth-off) sees the full tenant org map.
    """

    viewer_id: int | None
    unrestricted: bool


async def resolve_team_activity_scope(
    request: Request,
    session: AsyncSession,
    *,
    tenant_id: int,
) -> TeamActivityScope:
    """Resolve caller gate for the team-activity list route.

    Auth off → unrestricted. Hierarchy ``AREA_MANAGER`` → AM-scoped (even though
    AM is an admin-plane principal). Other admin principals → unrestricted.
    PO device → PO-scoped. All others → 403.
    """
    settings = get_settings()
    if not settings.spice_auth_enabled:
        return TeamActivityScope(viewer_id=None, unrestricted=True)

    user = _require_spice_user(request)
    viewer_id = user.id

    if viewer_id is not None:
        org = (await org_user_index(session, tenant_id=tenant_id)).get(viewer_id)
        if org is not None and org.role == HierarchyRole.AREA_MANAGER.value:
            return TeamActivityScope(viewer_id=viewer_id, unrestricted=False)

    if is_admin_principal(user):
        return TeamActivityScope(viewer_id=viewer_id, unrestricted=True)

    if is_device_principal(user):
        if not is_organizer_principal(user):
            raise AppError(
                ErrorCode.FORBIDDEN.value,
                "only program organizers may access team activity",
                status=403,
            )
        if viewer_id is None:
            raise AppError(ErrorCode.FORBIDDEN.value, "authenticated user has no id", status=403)
        return TeamActivityScope(viewer_id=viewer_id, unrestricted=False)

    raise AppError(ErrorCode.FORBIDDEN.value, "principal has no recognized role", status=403)


@dataclass(frozen=True, slots=True)
class PublishedModuleCompletionsScope:
    """Caller gate for ``GET /dashboard/published-module-completions``.

    Admin / auth-off → ``unrestricted`` (all tenant tree SKs). Area Manager →
    scoped to descendant SKs. Device principals (including organizer POs) are
    denied.
    """

    viewer_id: int | None
    unrestricted: bool


async def resolve_published_module_completions_scope(
    request: Request,
    session: AsyncSession,
    *,
    tenant_id: int,
) -> PublishedModuleCompletionsScope:
    """Resolve caller gate for published-module-completions.

    Auth off → unrestricted. Hierarchy ``AREA_MANAGER`` → AM-scoped. Other
    admin principals → unrestricted. All device principals → 403.
    """
    settings = get_settings()
    if not settings.spice_auth_enabled:
        return PublishedModuleCompletionsScope(viewer_id=None, unrestricted=True)

    user = _require_spice_user(request)
    viewer_id = user.id

    if viewer_id is not None:
        org = (await org_user_index(session, tenant_id=tenant_id)).get(viewer_id)
        if org is not None and org.role == HierarchyRole.AREA_MANAGER.value:
            return PublishedModuleCompletionsScope(viewer_id=viewer_id, unrestricted=False)

    if is_admin_principal(user):
        return PublishedModuleCompletionsScope(viewer_id=viewer_id, unrestricted=True)

    if is_device_principal(user):
        raise AppError(
            ErrorCode.FORBIDDEN.value,
            "only admins and area managers may access published module completions",
            status=403,
        )

    raise AppError(ErrorCode.FORBIDDEN.value, "principal has no recognized role", status=403)


def resolve_tenant_id_for_dashboard(
    request: Request,
    requested_tenant_id: int | None = None,
) -> int:
    """Resolve tenant scope for dashboard analytics.

    Selected tenant comes from authenticate ``userDetail.country.tenantId``
    via middleware.
    """
    _ = requested_tenant_id
    return get_selected_tenant_id(request)
