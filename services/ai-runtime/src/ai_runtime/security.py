"""Shared internal API authentication helpers."""

from __future__ import annotations

import hmac
import logging

from fastapi import Request
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError

from ai_runtime.config import get_settings

logger = logging.getLogger(__name__)

_TENANT_HEADER = "TenantId"


def require_internal_token(request: Request) -> None:
    """Validate platform -> ai-runtime shared-secret token."""
    settings = get_settings()
    token = request.headers.get("X-Internal-Token", "")
    if not hmac.compare_digest(token, settings.internal_token):
        raise AppError(
            ErrorCode.INTERNAL_TOKEN_INVALID.value,
            "Invalid or missing internal token",
            status=401,
        )
    # Tenant is context/logging only; ai-runtime remains datastore-stateless.
    tenant_raw = request.headers.get(_TENANT_HEADER)
    if tenant_raw is not None:
        logger.debug("ai-runtime request TenantId=%s path=%s", tenant_raw, request.url.path)
