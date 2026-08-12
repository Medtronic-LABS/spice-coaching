"""Persistence for CHW module training requests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.chw_training_request import CHWTrainingRequest
from platform_service.db.tenant_scope import tenant_scope_filter


def _now() -> datetime:
    return datetime.now(UTC)


class TrainingRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        chw_id: int,
        module_id: UUID | None,
        requested_module_name: str | None,
        reason: str | None,
        tenant_id: int = DEFAULT_TENANT_ID,
        submitted_at: datetime | None = None,
    ) -> CHWTrainingRequest:
        row = CHWTrainingRequest(
            chw_id=chw_id,
            module_id=module_id,
            requested_module_name=requested_module_name,
            reason=reason,
            submitted_at=submitted_at or _now(),
            tenant_id=tenant_id,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def has_for_module(self, *, chw_id: int, module_id: UUID) -> bool:
        result = await self._session.execute(
            select(CHWTrainingRequest.id).where(
                CHWTrainingRequest.chw_id == chw_id,
                CHWTrainingRequest.module_id == module_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def has_for_custom_name(self, *, chw_id: int, requested_module_name: str) -> bool:
        normalized = requested_module_name.strip().lower()
        result = await self._session.execute(
            select(CHWTrainingRequest.id).where(
                CHWTrainingRequest.chw_id == chw_id,
                CHWTrainingRequest.module_id.is_(None),
                func.lower(func.trim(CHWTrainingRequest.requested_module_name)) == normalized,
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_for_chw(
        self,
        *,
        chw_id: int,
        tenant_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CHWTrainingRequest]:
        stmt = (
            select(CHWTrainingRequest)
            .where(
                CHWTrainingRequest.chw_id == chw_id,
            )
            .order_by(CHWTrainingRequest.submitted_at.desc())
        )
        if tenant_id is not None:
            stmt = stmt.where(tenant_scope_filter(CHWTrainingRequest.tenant_id, tenant_id))
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        elif offset:
            stmt = stmt.offset(offset)
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_all(
        self,
        *,
        tenant_id: int | None = None,
    ) -> list[CHWTrainingRequest]:
        """Return all training requests, optionally scoped to a tenant."""
        stmt = select(CHWTrainingRequest).order_by(CHWTrainingRequest.submitted_at.desc())
        if tenant_id is not None:
            stmt = stmt.where(CHWTrainingRequest.tenant_id == tenant_id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def distinct_tenant_ids(self) -> list[int]:
        """Distinct tenant_ids that have training requests."""
        stmt = select(CHWTrainingRequest.tenant_id).distinct()
        return [tid for (tid,) in (await self._session.execute(stmt)).all()]
