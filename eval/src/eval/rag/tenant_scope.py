"""Bind selected tenant for eval runs (mirrors worker/API tenant context)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from platform_service.auth.tenant_context import using_selected_tenant


@contextmanager
def eval_tenant_scope(tenant_id: int | None) -> Iterator[None]:
    """Bind tenant for outbound ai-runtime headers and LLM cache when set."""
    if tenant_id is None:
        yield
        return
    with using_selected_tenant(tenant_id):
        yield
