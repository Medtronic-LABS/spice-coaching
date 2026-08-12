"""Middleware that validates SPICE JWTs via auth-service ``/authenticate``.

Also resolves the selected tenant from authenticate
``userDetail.country.tenantId`` (request ``TenantId`` is ignored for selection).
"""

from __future__ import annotations

import base64
import logging

from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError, problem_json_response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from platform_service.auth.hierarchy_auth import enforce_hierarchy_principal
from platform_service.auth.tenant_context import (
    DEFAULT_SELECTED_TENANT_ID,
    selected_tenant_from_user,
    set_context_selected_tenant_id,
)
from platform_service.config import get_settings
from platform_service.db.base import SessionLocal
from platform_service.deps import get_spice_auth_client
from platform_service.integrations.spice_auth_client import SpiceAuthClient, SpiceAuthError

logger = logging.getLogger(__name__)

WEB_CLIENTS = frozenset(
    {
        "web",
        "admin",
        "cfr",
        "insights",
        "cfr_user",
        "cfr_admin",
        "cfr_quicksight_admin",
        "spice web",
        "cfr web",
    }
)


def _set_tenant_context(request: Request, *, selected_tenant_id: int) -> None:
    request.state.selected_tenant_id = selected_tenant_id
    set_context_selected_tenant_id(selected_tenant_id)


class SpiceAuthMiddleware(BaseHTTPMiddleware):
    """When ``spice_auth_enabled``, validate every non-exempt request."""

    def __init__(self, app, client: SpiceAuthClient | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._client = client

    def _get_client(self) -> SpiceAuthClient:
        if self._client is not None:
            return self._client
        return get_spice_auth_client()

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        settings = get_settings()
        if not settings.spice_auth_enabled:
            _set_tenant_context(
                request,
                selected_tenant_id=DEFAULT_SELECTED_TENANT_ID,
            )
            return await call_next(request)

        if request.url.path in settings.spice_auth_exempt_path_set:
            _set_tenant_context(
                request,
                selected_tenant_id=DEFAULT_SELECTED_TENANT_ID,
            )
            return await call_next(request)

        client_header = request.headers.get("client")
        client_name = (client_header or "").strip() or settings.spice_auth_default_client
        request.state.client = client_name

        authorization = request.headers.get("authorization")
        auth_cookie_val = request.headers.get("auth-cookie") or request.cookies.get("auth-cookie")
        using_web_cookie = False

        if client_name.lower() in WEB_CLIENTS or client_name.lower().startswith("web"):
            if not authorization and auth_cookie_val:
                try:
                    decoded = base64.b64decode(auth_cookie_val).decode("utf-8")
                    if decoded.startswith("Bearer "):
                        authorization = decoded
                    else:
                        authorization = f"Bearer {decoded}"
                    using_web_cookie = True
                except Exception as exc:
                    print(exc)
                    logger.warning("Failed to base64 decode auth-cookie header/cookie")

        try:
            SpiceAuthClient.validate_authorization_header(authorization)
            contexts = await self._get_client().authenticate(
                authorization=authorization,  # type: ignore[arg-type]
                client=client_name,
                auth_cookie=auth_cookie_val,
            )
        except SpiceAuthError as exc:
            code = (
                ErrorCode.NOT_AUTHENTICATED.value
                if exc.status_code == 401
                else ErrorCode.FORBIDDEN.value
                if exc.status_code == 403
                else ErrorCode.BAD_REQUEST.value
            )
            return problem_json_response(
                code=code,
                detail=str(exc.detail),
                status=exc.status_code,
                instance=str(request.url.path),
            )

        if contexts.user_detail:
            contexts.user_detail.client = client_name

        request.state.spice_contexts = contexts
        request.state.spice_user = contexts.user_detail

        selected_tenant_id = selected_tenant_from_user(contexts.user_detail)
        if selected_tenant_id is None:
            return problem_json_response(
                code=ErrorCode.NOT_AUTHENTICATED.value,
                detail="authenticate response missing userDetail.country.tenantId",
                status=401,
                instance=str(request.url.path),
            )

        _set_tenant_context(
            request,
            selected_tenant_id=selected_tenant_id,
        )

        user_detail = contexts.user_detail
        if user_detail is None:
            return problem_json_response(
                code=ErrorCode.NOT_AUTHENTICATED.value,
                detail="authenticate response missing userDetail",
                status=401,
                instance=str(request.url.path),
            )

        try:
            async with SessionLocal() as session:
                await enforce_hierarchy_principal(session, user_detail)
        except AppError as exc:
            return problem_json_response(
                code=exc.code,
                detail=exc.detail,
                status=exc.status,
                instance=str(request.url.path),
            )

        response = await call_next(request)

        if using_web_cookie and authorization:
            token_str = authorization[len("Bearer ") :].strip()
            encoded_cookie = base64.b64encode(token_str.encode("utf-8")).decode("utf-8")
            response.set_cookie(
                key="auth-cookie",
                value=encoded_cookie,
                max_age=1800,
                path="/",
                httponly=True,
                samesite="lax",
                secure=True if settings.app_env in ("staging", "production") else False,
            )

        return response
