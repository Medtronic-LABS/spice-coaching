"""Admin badge catalog orchestration and validation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from mc_contracts.badges import (
    BadgeCreateRequest,
    BadgeListResponse,
    BadgeModuleRef,
    BadgeResponse,
    BadgeUpdateRequest,
)
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.badge import Badge
from platform_service.db.repositories.badge_repository import (
    DEFAULT_BADGE_SORT_BY,
    DEFAULT_BADGE_SORT_DIR,
    BadgeRepository,
)
from platform_service.module_domains import catalog_domain_label


class BadgeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BadgeRepository(session)

    async def create(
        self,
        body: BadgeCreateRequest,
        *,
        tenant_id: int = 0,
        actor: str | None = None,
    ) -> BadgeResponse:
        module_ids = list(dict.fromkeys(body.module_ids))
        domain = await self._resolve_domain(body.domain)
        await self._validate_write(body.name, body.sequence, module_ids)
        badge = await self._repo.create(
            name=body.name,
            domain=domain,
            image_storage_path=body.image_storage_path,
            sequence=body.sequence,
            tenant_id=tenant_id,
            created_by=actor,
        )
        await self._repo.replace_module_links(badge.id, module_ids)
        await self._session.commit()
        await self._session.refresh(badge)
        return await self._to_response(badge)

    async def get(self, badge_id: UUID) -> BadgeResponse:
        badge = await self._repo.get_active(badge_id)
        if badge is None:
            raise AppError(
                ErrorCode.BADGE_NOT_FOUND.value,
                f"Badge '{badge_id}' not found.",
                status=404,
            )
        return await self._to_response(badge)

    async def list(
        self,
        *,
        domain: str | None,
        created_by: list[str] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        module_titles: list[str] | None = None,
        q: str | None,
        sort_by: str = DEFAULT_BADGE_SORT_BY,
        sort_dir: str = DEFAULT_BADGE_SORT_DIR,
        limit: int,
        offset: int,
    ) -> BadgeListResponse:
        badges, total = await self._repo.list_active(
            domain=domain,
            created_by=created_by,
            created_from=created_from,
            created_to=created_to,
            module_titles=module_titles,
            q=q,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
        modules_by_badge = await self._repo.list_modules_for_badges([b.id for b in badges])
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        return BadgeListResponse(
            badges=[
                self._badge_response(
                    badge,
                    modules_by_badge.get(badge.id, []),
                )
                for badge in badges
            ],
            total=total,
            total_pages=total_pages,
            limit=limit,
            offset=offset,
        )

    async def update(
        self,
        badge_id: UUID,
        body: BadgeUpdateRequest,
        *,
        actor: str | None = None,
    ) -> BadgeResponse:
        badge = await self._repo.get_active(badge_id)
        if badge is None:
            raise AppError(
                ErrorCode.BADGE_NOT_FOUND.value,
                f"Badge '{badge_id}' not found.",
                status=404,
            )
        module_ids = list(dict.fromkeys(body.module_ids))
        domain = await self._resolve_domain(body.domain)
        await self._validate_write(
            body.name,
            body.sequence if "sequence" in body.model_fields_set else badge.sequence,
            module_ids,
            exclude_badge_id=badge_id,
        )
        await self._repo.update(
            badge,
            name=body.name,
            domain=domain,
            image_storage_path=body.image_storage_path,
            updated_by=actor,
            update_sequence="sequence" in body.model_fields_set,
            sequence=body.sequence,
        )
        await self._repo.replace_module_links(badge.id, module_ids)
        await self._session.commit()
        await self._session.refresh(badge)
        return await self._to_response(badge)

    async def soft_delete(self, badge_id: UUID, *, actor: str | None = None) -> None:
        badge = await self._repo.get_active(badge_id)
        if badge is None:
            raise AppError(
                ErrorCode.BADGE_NOT_FOUND.value,
                f"Badge '{badge_id}' not found.",
                status=404,
            )
        await self._repo.soft_delete(badge, updated_by=actor)
        await self._session.commit()

    async def _resolve_domain(self, domain: str) -> str:
        """Normalize and require the label to already exist on a module."""
        normalized = catalog_domain_label(domain)
        if normalized is None:
            raise AppError(
                ErrorCode.BADGE_DOMAIN_INVALID.value,
                "Domain must be a non-empty snake_case label (e.g. hypertension, sample_domain).",
                status=400,
            )
        if not await self._repo.domain_exists_on_module(normalized):
            raise AppError(
                ErrorCode.BADGE_DOMAIN_INVALID.value,
                f"Domain '{normalized}' does not exist on any module.",
                status=400,
            )
        return normalized

    async def _validate_write(
        self,
        name: str,
        sequence: int | None,
        module_ids: list[UUID],
        *,
        exclude_badge_id: UUID | None = None,
    ) -> None:
        if await self._repo.exists_active_name(name, exclude_badge_id=exclude_badge_id):
            raise AppError(
                ErrorCode.BADGE_NAME_CONFLICT.value,
                f"An active badge named '{name}' already exists.",
                status=409,
            )
        if sequence is not None and await self._repo.exists_active_sequence(
            sequence,
            exclude_badge_id=exclude_badge_id,
        ):
            raise AppError(
                ErrorCode.BADGE_SEQUENCE_CONFLICT.value,
                f"Sequence {sequence} is already used by another active badge.",
                status=409,
            )
        unique_module_ids = list(dict.fromkeys(module_ids))
        published = await self._repo.list_published_module_ids(unique_module_ids)
        missing_or_unpublished = [mid for mid in unique_module_ids if mid not in published]
        if missing_or_unpublished:
            raise AppError(
                ErrorCode.BADGE_MODULE_NOT_PUBLISHED.value,
                "All module_ids must refer to published modules. "
                f"Invalid: {', '.join(str(m) for m in missing_or_unpublished)}",
                status=400,
            )

    async def _to_response(self, badge: Badge) -> BadgeResponse:
        modules_by_badge = await self._repo.list_modules_for_badges([badge.id])
        return self._badge_response(badge, modules_by_badge.get(badge.id, []))

    def _badge_response(
        self,
        badge: Badge,
        linked_modules: list[tuple[UUID, dict[str, str]]],
    ) -> BadgeResponse:
        modules = [BadgeModuleRef(id=module_id, title=title) for module_id, title in linked_modules]
        return BadgeResponse(
            id=badge.id,
            name=badge.name,
            domain=badge.domain,
            image_storage_path=badge.image_storage_path,
            module_ids=[ref.id for ref in modules],
            modules=modules,
            status=badge.status,
            sequence=badge.sequence,
            created_at=badge.created_at,
            updated_at=badge.updated_at,
            created_by=badge.created_by,
            updated_by=badge.updated_by,
        )
