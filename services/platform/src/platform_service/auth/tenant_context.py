"""Selected-tenant resolution from authenticate ``userDetail.country.tenantId``."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar

from platform_service.auth.spice_context import SpiceUserContext

HEADER_TENANT_ID = "TenantId"
DEFAULT_SELECTED_TENANT_ID = 0

_selected_tenant_id_ctx: ContextVar[int] = ContextVar(
    "selected_tenant_id",
    default=DEFAULT_SELECTED_TENANT_ID,
)
_selected_tenant_bound_ctx: ContextVar[bool] = ContextVar(
    "selected_tenant_bound",
    default=False,
)


def get_context_selected_tenant_id() -> int:
    """Return the selected tenant bound for the current async/task context."""
    return _selected_tenant_id_ctx.get()


def set_context_selected_tenant_id(tenant_id: int) -> None:
    """Bind selected tenant for outbound calls (e.g. ai-runtime)."""
    _selected_tenant_id_ctx.set(tenant_id)


def require_selected_tenant_id() -> int:
    """Return the tenant explicitly bound via ``using_selected_tenant``.

    Ingest Stage C/D module create/merge must not fall back to the ContextVar
    default (``0``) or a hardcoded tenant — workers bind the initiating
    tenant before running the pipeline.
    """
    if not _selected_tenant_bound_ctx.get():
        raise ValueError("selected tenant is not bound; cannot create or merge ingest modules")
    return _selected_tenant_id_ctx.get()


@contextmanager
def using_selected_tenant(tenant_id: int) -> Iterator[int]:
    """Bind selected tenant for the duration of a worker/job scope, then reset."""
    token = _selected_tenant_id_ctx.set(tenant_id)
    bound_token = _selected_tenant_bound_ctx.set(True)
    try:
        yield tenant_id
    finally:
        _selected_tenant_bound_ctx.reset(bound_token)
        _selected_tenant_id_ctx.reset(token)


def selected_tenant_from_user(user: SpiceUserContext | None) -> int | None:
    """Return the coaching tenant from ``user.country.tenantId``, or ``None`` if absent."""
    if user is None or user.country is None:
        return None
    return user.country.tenant_id


def selected_tenant_from_header(headers: Mapping[str, str]) -> int | None:
    """Parse ``TenantId`` request header; return ``None`` if absent or invalid."""
    raw = headers.get(HEADER_TENANT_ID)
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def resolve_selected_tenant_when_auth_disabled(headers: Mapping[str, str]) -> int:
    """Resolve selected tenant when SPICE auth is disabled (local/dev)."""
    return selected_tenant_from_header(headers) or DEFAULT_SELECTED_TENANT_ID
