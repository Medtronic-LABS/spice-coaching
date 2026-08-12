"""Selected-tenant resolution from authenticate ``userDetail.country.tenantId``."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from platform_service.auth.spice_context import SpiceUserContext

HEADER_TENANT_ID = "TenantId"
DEFAULT_SELECTED_TENANT_ID = 0

_selected_tenant_id_ctx: ContextVar[int] = ContextVar(
    "selected_tenant_id",
    default=DEFAULT_SELECTED_TENANT_ID,
)


def get_context_selected_tenant_id() -> int:
    """Return the selected tenant bound for the current async/task context."""
    return _selected_tenant_id_ctx.get()


def set_context_selected_tenant_id(tenant_id: int) -> None:
    """Bind selected tenant for outbound calls (e.g. ai-runtime)."""
    _selected_tenant_id_ctx.set(tenant_id)


@contextmanager
def using_selected_tenant(tenant_id: int) -> Iterator[int]:
    """Bind selected tenant for the duration of a worker/job scope, then reset."""
    token = _selected_tenant_id_ctx.set(tenant_id)
    try:
        yield tenant_id
    finally:
        _selected_tenant_id_ctx.reset(token)


def selected_tenant_from_user(user: SpiceUserContext | None) -> int | None:
    """Return the coaching tenant from ``user.country.tenantId``, or ``None`` if absent."""
    if user is None or user.country is None:
        return None
    return user.country.tenant_id
