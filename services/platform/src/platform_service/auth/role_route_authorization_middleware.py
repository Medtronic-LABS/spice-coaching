"""Middleware enforcing DB role → path-template authorization."""

from __future__ import annotations

import logging

from mc_contracts.errors import ErrorCode
from mc_foundation.logging import get_security_logger
from mc_foundation.problem import problem_json_response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from platform_service.auth.path_template import match_path_template, normalize_relative_path
from platform_service.auth.spice_context import SpiceUserContext
from platform_service.config import get_settings
from platform_service.db.base import SessionLocal
from platform_service.db.repositories.role_route_access_repository import (
    RoleRouteAccessRepository,
)

logger = logging.getLogger(__name__)
security_logger = get_security_logger()

FORBIDDEN_DETAIL = "insufficient role for this API"


def _deny_authorization(
    request: Request,
    *,
    user_id: int | None,
    role_id: int | None,
    matched_template: str | None,
) -> Response:
    security_logger.warning(
        "authorization_denied",
        extra={
            "event": "authorization_denied",
            "path": str(request.url.path),
            "user_id": user_id,
            "role_id": role_id,
            "matched_template": matched_template,
        },
    )
    return problem_json_response(
        code=ErrorCode.FORBIDDEN.value,
        detail=FORBIDDEN_DETAIL,
        status=403,
        instance=str(request.url.path),
    )


class RoleRouteAuthorizationMiddleware(BaseHTTPMiddleware):
    """When SPICE auth is enabled, require a DB role grant for the request path."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        settings = get_settings()
        if not settings.spice_auth_enabled:
            return await call_next(request)

        if request.url.path in settings.spice_auth_exempt_path_set:
            return await call_next(request)

        user: SpiceUserContext | None = getattr(request.state, "spice_user", None)
        if user is None:
            return await call_next(request)

        if user.is_super_user or user.is_job_user:
            return await call_next(request)

        role_id = getattr(request.state, "hierarchy_role_id", None)
        if role_id is None:
            return _deny_authorization(
                request,
                user_id=user.id,
                role_id=None,
                matched_template=None,
            )

        relative = normalize_relative_path(
            str(request.url.path),
            settings.api_root_path_normalized,
        )

        async with SessionLocal() as session:
            repo = RoleRouteAccessRepository(session)
            all_templates = await repo.list_all_path_templates()
            granted = frozenset(await repo.list_path_templates_for_role(role_id))

        matched = match_path_template(relative, all_templates)
        if matched is None or matched not in granted:
            return _deny_authorization(
                request,
                user_id=user.id,
                role_id=role_id,
                matched_template=matched,
            )

        return await call_next(request)
