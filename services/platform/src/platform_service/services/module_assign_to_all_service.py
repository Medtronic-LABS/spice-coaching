"""Admin service for the module ``assign_to_all`` flag and its linked video documents."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.module import Module
from platform_service.db.repositories.module_lifecycle_repository import ModuleNotFoundError
from platform_service.db.repositories.source_repository import SourceRepository


class ModuleAssignToAllService:
    """Set ``assign_to_all`` on a module and on its linked ``video`` source documents.

    Videos reach SKs through ``assigned_documents`` (not through the module), so the flag
    is mirrored onto the module's video documents to keep both delivery paths in step.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_for_module(
        self,
        module_id: UUID,
        *,
        assign_to_all: bool,
        updated_by: int | None = None,
    ) -> Module:
        module = await self._session.get(Module, module_id)
        if module is None:
            raise ModuleNotFoundError(module_id)
        module.assign_to_all = assign_to_all
        await SourceRepository(self._session).set_assign_to_all_for_videos(
            list(module.source_document_ids or []),
            assign_to_all=assign_to_all,
            updated_by=updated_by,
        )
        await self._session.flush()
        return module
