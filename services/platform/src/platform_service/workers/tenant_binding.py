"""Resolve tenant ids for Celery worker ContextVar binding."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar
from uuid import UUID

from platform_service.auth.tenant_context import DEFAULT_SELECTED_TENANT_ID, using_selected_tenant
from platform_service.db.base import SessionLocal
from platform_service.db.models.ingest_batch import IngestBatch
from platform_service.db.models.module import Module
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.services.module_completion.telemetry_parsing import coerce_tenant_id

R = TypeVar("R")


def payload_tenant_id(payload: dict[str, Any]) -> int:
    """Tenant from a telemetry/job payload, or default when absent."""
    resolved = coerce_tenant_id(payload.get("tenant_id"))
    return resolved if resolved is not None else DEFAULT_SELECTED_TENANT_ID


async def source_document_tenant_id(source_document_id: UUID) -> int:
    """Load tenant_id from a source_document row (default when missing)."""
    async with SessionLocal() as session:
        doc = await SourceRepository(session).get_source_document(source_document_id)
        if doc is None:
            return DEFAULT_SELECTED_TENANT_ID
        return doc.tenant_id


async def ingest_batch_tenant_id(batch_id: UUID) -> int:
    """Load tenant_id from an ingest_batch row (default when missing)."""
    async with SessionLocal() as session:
        batch = await session.get(IngestBatch, batch_id)
        if batch is None:
            return DEFAULT_SELECTED_TENANT_ID
        return batch.tenant_id


async def module_tenant_id(module_id: UUID) -> int:
    """Load tenant_id from a module row (default when missing)."""
    async with SessionLocal() as session:
        module = await session.get(Module, module_id)
        if module is None:
            return DEFAULT_SELECTED_TENANT_ID
        return module.tenant_id


def with_module_tenant(
    fn: Callable[..., Awaitable[R]],
) -> Callable[..., Awaitable[R]]:
    """Bind ContextVar from ``module_id`` (first positional / kwarg) for the call."""

    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> R:
        module_id = kwargs.get("module_id")
        if module_id is None and args:
            module_id = args[0]
        if not isinstance(module_id, UUID):
            module_id = UUID(str(module_id))
        tenant_id = await module_tenant_id(module_id)
        with using_selected_tenant(tenant_id):
            return await fn(*args, **kwargs)

    return wrapper
