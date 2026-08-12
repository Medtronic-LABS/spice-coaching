"""Repository for badge catalog and badge ↔ module links."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.badge import BADGE_STATUS_ACTIVE, BADGE_STATUS_DELETED, Badge, BadgeModule
from platform_service.db.models.module import Module
from platform_service.db.module_availability import LIFECYCLE_PUBLISHED
from platform_service.localized import deployment_locales

BADGE_SORT_KEYS = frozenset({"created_at", "sequence"})
BADGE_SORT_DIRS = frozenset({"asc", "desc"})
DEFAULT_BADGE_SORT_BY = "created_at"
DEFAULT_BADGE_SORT_DIR = "desc"


def _escape_ilike_pattern(value: str) -> str:
    """Escape SQL ``LIKE``/``ILIKE`` wildcards in user input."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _badge_order_clauses(sort_by: str, sort_dir: str) -> list[Any]:
    descending = sort_dir == "desc"
    if sort_by == "sequence":
        primary = Badge.sequence.desc().nullslast() if descending else Badge.sequence.asc().nullslast()
    else:
        primary = Badge.created_at.desc() if descending else Badge.created_at.asc()
    return [primary, Badge.id.asc()]


class BadgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        name: str,
        domain: str,
        image_storage_path: str,
        sequence: int | None = None,
        tenant_id: int = DEFAULT_TENANT_ID,
        created_by: str | None = None,
    ) -> Badge:
        badge = Badge(
            name=name,
            domain=domain,
            image_storage_path=image_storage_path,
            sequence=sequence,
            status=BADGE_STATUS_ACTIVE,
            tenant_id=tenant_id,
            created_by=created_by,
            updated_by=created_by,
        )
        self._session.add(badge)
        await self._session.flush()
        return badge

    async def get_active(self, badge_id: UUID) -> Badge | None:
        stmt = select(Badge).where(Badge.id == badge_id, Badge.status == BADGE_STATUS_ACTIVE)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_active(
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
    ) -> tuple[list[Badge], int]:
        filters = [Badge.status == BADGE_STATUS_ACTIVE]
        if domain is not None:
            filters.append(Badge.domain == domain)
        if created_by:
            filters.append(Badge.created_by.in_(created_by))
        if created_from is not None:
            filters.append(Badge.created_at >= created_from)
        if created_to is not None:
            filters.append(Badge.created_at <= created_to)
        if q is not None and q.strip():
            filters.append(Badge.name.ilike(f"%{q.strip()}%"))
        if module_titles:
            primary = deployment_locales()
            title_clauses = [
                Module.title_localized[primary].astext.ilike(
                    f"%{_escape_ilike_pattern(title)}%",
                    escape="\\",
                )
                for title in module_titles
            ]
            module_link_exists = exists(
                select(1)
                .select_from(BadgeModule)
                .join(Module, Module.id == BadgeModule.module_id)
                .where(BadgeModule.badge_id == Badge.id, or_(*title_clauses))
            )
            filters.append(module_link_exists)

        count_stmt = select(func.count()).select_from(Badge).where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())

        stmt = (
            select(Badge)
            .where(*filters)
            .order_by(*_badge_order_clauses(sort_by, sort_dir))
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return rows, total

    async def update(
        self,
        badge: Badge,
        *,
        name: str,
        domain: str,
        image_storage_path: str,
        updated_by: str | None = None,
        update_sequence: bool = False,
        sequence: int | None = None,
    ) -> Badge:
        badge.name = name
        badge.domain = domain
        badge.image_storage_path = image_storage_path
        badge.updated_by = updated_by
        if update_sequence:
            badge.sequence = sequence
        await self._session.flush()
        return badge

    async def soft_delete(self, badge: Badge, *, updated_by: str | None = None) -> Badge:
        badge.status = BADGE_STATUS_DELETED
        badge.updated_by = updated_by
        await self._session.flush()
        return badge

    async def replace_module_links(self, badge_id: UUID, module_ids: list[UUID]) -> None:
        await self._session.execute(delete(BadgeModule).where(BadgeModule.badge_id == badge_id))
        for module_id in module_ids:
            self._session.add(BadgeModule(badge_id=badge_id, module_id=module_id))
        await self._session.flush()

    async def list_module_ids(self, badge_id: UUID) -> list[UUID]:
        stmt = (
            select(BadgeModule.module_id)
            .where(BadgeModule.badge_id == badge_id)
            .order_by(BadgeModule.module_id)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_module_ids_for_badges(self, badge_ids: list[UUID]) -> dict[UUID, list[UUID]]:
        if not badge_ids:
            return {}
        stmt = (
            select(BadgeModule.badge_id, BadgeModule.module_id)
            .where(BadgeModule.badge_id.in_(badge_ids))
            .order_by(BadgeModule.badge_id, BadgeModule.module_id)
        )
        result: dict[UUID, list[UUID]] = {badge_id: [] for badge_id in badge_ids}
        for badge_id, module_id in (await self._session.execute(stmt)).all():
            result[badge_id].append(module_id)
        return result

    async def list_modules_for_badges(
        self,
        badge_ids: list[UUID],
    ) -> dict[UUID, list[tuple[UUID, dict[str, str]]]]:
        """Linked modules with localized titles, ordered by module id per badge."""
        if not badge_ids:
            return {}
        stmt = (
            select(BadgeModule.badge_id, Module.id, Module.title_localized)
            .join(Module, Module.id == BadgeModule.module_id)
            .where(BadgeModule.badge_id.in_(badge_ids))
            .order_by(BadgeModule.badge_id, Module.id)
        )
        result: dict[UUID, list[tuple[UUID, dict[str, str]]]] = {badge_id: [] for badge_id in badge_ids}
        for badge_id, module_id, title_localized in (await self._session.execute(stmt)).all():
            title = title_localized if isinstance(title_localized, dict) else {}
            result[badge_id].append((module_id, title))
        return result

    async def list_published_module_ids_for_badges(self, badge_ids: list[UUID]) -> dict[UUID, list[UUID]]:
        """Linked module ids limited to currently published module versions."""
        if not badge_ids:
            return {}
        stmt = (
            select(BadgeModule.badge_id, BadgeModule.module_id)
            .join(Module, Module.id == BadgeModule.module_id)
            .where(
                BadgeModule.badge_id.in_(badge_ids),
                Module.lifecycle_status == LIFECYCLE_PUBLISHED,
            )
            .order_by(BadgeModule.badge_id, BadgeModule.module_id)
        )
        result: dict[UUID, list[UUID]] = {badge_id: [] for badge_id in badge_ids}
        for badge_id, module_id in (await self._session.execute(stmt)).all():
            result[badge_id].append(module_id)
        return result

    async def exists_active_name(self, name: str, *, exclude_badge_id: UUID | None = None) -> bool:
        stmt = select(Badge.id).where(Badge.name == name, Badge.status == BADGE_STATUS_ACTIVE)
        if exclude_badge_id is not None:
            stmt = stmt.where(Badge.id != exclude_badge_id)
        return (await self._session.execute(stmt.limit(1))).scalar_one_or_none() is not None

    async def exists_active_sequence(
        self,
        sequence: int,
        *,
        exclude_badge_id: UUID | None = None,
    ) -> bool:
        stmt = select(Badge.id).where(
            Badge.sequence == sequence,
            Badge.status == BADGE_STATUS_ACTIVE,
        )
        if exclude_badge_id is not None:
            stmt = stmt.where(Badge.id != exclude_badge_id)
        return (await self._session.execute(stmt.limit(1))).scalar_one_or_none() is not None

    async def domain_exists_on_module(self, domain: str) -> bool:
        """True when at least one module row uses this catalog domain label."""
        stmt = select(Module.id).where(Module.domain == domain).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def list_published_module_ids(self, module_ids: list[UUID]) -> set[UUID]:
        if not module_ids:
            return set()
        stmt = select(Module.id).where(
            Module.id.in_(module_ids),
            Module.lifecycle_status == LIFECYCLE_PUBLISHED,
        )
        return set((await self._session.execute(stmt)).scalars().all())

    async def list_active_badge_ids_for_module(
        self,
        *,
        module_id: UUID,
        tenant_id: int,
    ) -> list[UUID]:
        """Active badges in ``tenant_id`` that link the given module version."""
        stmt = (
            select(Badge.id)
            .join(BadgeModule, BadgeModule.badge_id == Badge.id)
            .where(
                BadgeModule.module_id == module_id,
                Badge.status == BADGE_STATUS_ACTIVE,
                Badge.tenant_id == tenant_id,
            )
            .order_by(Badge.id)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_active_for_tenant(self, tenant_id: int) -> list[Badge]:
        """Return all active badges for a tenant ordered by sequence nulls last, created_at desc, id asc."""
        stmt = (
            select(Badge)
            .where(
                Badge.status == BADGE_STATUS_ACTIVE,
                Badge.tenant_id == tenant_id,
            )
            .order_by(
                Badge.sequence.asc().nullslast(),
                Badge.created_at.desc(),
                Badge.id.asc(),
            )
        )
        return list((await self._session.execute(stmt)).scalars().all())
