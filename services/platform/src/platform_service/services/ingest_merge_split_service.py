"""Admin ingest split-merge — keep primary dual-path module, retire secondary."""

from dataclasses import dataclass
from uuid import UUID

from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.module import Module
from platform_service.db.module_availability import (
    LIFECYCLE_DRAFT,
    LIFECYCLE_REVIEW_PENDING,
)
from platform_service.db.repositories.module_repository import (
    ModuleNotFoundError,
    ModuleRepository,
)


@dataclass(frozen=True)
class IngestMergeSplitResult:
    primary_module_id: UUID
    secondary_module_id: UUID
    source_module_id: UUID | None
    primary_lifecycle_status: str
    secondary_lifecycle_status: str


class IngestMergeSplitService:
    """Keep primary in its own family as draft; retire secondary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._modules = ModuleRepository(session)

    async def split(
        self,
        module_id: UUID,
        *,
        retired_by_user_id: int | None = None,
    ) -> IngestMergeSplitResult:
        primary = await self._session.get(Module, module_id)
        if primary is None:
            raise AppError(
                ErrorCode.MODULE_NOT_FOUND.value,
                "module not found",
                status=404,
            )

        if primary.merge_secondary_module_id is None:
            raise AppError(
                ErrorCode.MERGE_SPLIT_NOT_PRIMARY.value,
                "module is not a dual-path merge primary",
                status=400,
            )

        if primary.lifecycle_status != LIFECYCLE_REVIEW_PENDING:
            raise AppError(
                ErrorCode.MERGE_SPLIT_NOT_REVIEW_PENDING.value,
                "split is only allowed while the primary is review_pending",
                status=409,
            )

        secondary = await self._session.get(Module, primary.merge_secondary_module_id)
        if secondary is None:
            raise AppError(
                ErrorCode.MODULE_NOT_FOUND.value,
                "secondary merge module not found",
                status=404,
            )
        if secondary.lifecycle_status != LIFECYCLE_REVIEW_PENDING:
            raise AppError(
                ErrorCode.MERGE_SPLIT_SECONDARY_UNAVAILABLE.value,
                "secondary merge module is not review_pending",
                status=409,
            )

        source_id = primary.merge_source_module_id or secondary.merge_source_module_id

        primary.lifecycle_status = LIFECYCLE_DRAFT
        try:
            await self._modules.retire_module(secondary.id, retired_by_user_id=retired_by_user_id)
        except ModuleNotFoundError as exc:
            raise AppError(
                ErrorCode.MODULE_NOT_FOUND.value,
                str(exc),
                status=404,
            ) from exc

        await self._session.flush()
        await self._session.commit()

        return IngestMergeSplitResult(
            primary_module_id=primary.id,
            secondary_module_id=secondary.id,
            source_module_id=source_id,
            primary_lifecycle_status=primary.lifecycle_status,
            secondary_lifecycle_status=secondary.lifecycle_status,
        )
