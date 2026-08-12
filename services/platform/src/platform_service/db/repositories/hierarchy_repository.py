"""Repository for district, upazila, and hierarchy users tables."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.district import District
from platform_service.db.models.hierarchy_user import HierarchyUser
from platform_service.db.models.upazila import Upazila
from platform_service.db.models.user_upazila import UserUpazila


def _escape_ilike_pattern(value: str) -> str:
    """Escape SQL ``LIKE``/``ILIKE`` wildcards in user input."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class HierarchyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Districts ──────────────────────────────────────────────────────────

    async def create_district(
        self,
        *,
        name: str,
        tenant_id: int,
        actor: str,
    ) -> District:
        district = District(
            name=name,
            tenant_id=tenant_id,
            created_by=actor,
            updated_by=actor,
        )
        self._session.add(district)
        await self._session.flush()
        return district

    async def get_district(self, district_id: int, *, tenant_id: int) -> District | None:
        stmt = select(District).where(
            District.id == district_id,
            District.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_district_by_id(self, district_id: int) -> District | None:
        stmt = select(District).where(District.id == district_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_districts_by_ids(
        self,
        district_ids: set[int],
        *,
        tenant_id: int,
    ) -> dict[int, District]:
        if not district_ids:
            return {}
        stmt = select(District).where(
            District.tenant_id == tenant_id,
            District.id.in_(district_ids),
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return {d.id: d for d in rows}

    async def list_districts(
        self,
        *,
        tenant_id: int,
        name_query: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[District], int]:
        filters = [District.tenant_id == tenant_id]
        if name_query:
            pattern = f"%{_escape_ilike_pattern(name_query.strip())}%"
            filters.append(District.name.ilike(pattern, escape="\\"))
        count_stmt = select(func.count()).select_from(District).where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())
        stmt = select(District).where(*filters).order_by(District.id.asc()).limit(limit).offset(offset)
        rows = list((await self._session.execute(stmt)).scalars().all())
        return rows, total

    async def update_district(
        self,
        district: District,
        *,
        name: str,
        actor: str,
    ) -> District:
        district.name = name
        district.updated_by = actor
        await self._session.flush()
        return district

    async def delete_district(self, district: District) -> None:
        await self._session.delete(district)
        await self._session.flush()

    # ── Upazilas ───────────────────────────────────────────────────────────

    async def create_upazila(
        self,
        *,
        name: str,
        district_id: int,
        tenant_id: int,
        actor: str,
    ) -> Upazila:
        upazila = Upazila(
            name=name,
            district_id=district_id,
            tenant_id=tenant_id,
            created_by=actor,
            updated_by=actor,
        )
        self._session.add(upazila)
        await self._session.flush()
        return upazila

    async def get_upazila(self, upazila_id: int, *, tenant_id: int) -> Upazila | None:
        stmt = select(Upazila).where(
            Upazila.id == upazila_id,
            Upazila.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_upazilas_by_ids(self, upazila_ids: list[int], *, tenant_id: int) -> list[Upazila]:
        if not upazila_ids:
            return []
        stmt = select(Upazila).where(
            Upazila.id.in_(upazila_ids),
            Upazila.tenant_id == tenant_id,
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_upazilas(
        self,
        *,
        tenant_id: int,
        district_id: int | None = None,
        name_query: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Upazila], int]:
        filters = [Upazila.tenant_id == tenant_id]
        if district_id is not None:
            filters.append(Upazila.district_id == district_id)
        if name_query:
            pattern = f"%{_escape_ilike_pattern(name_query.strip())}%"
            filters.append(Upazila.name.ilike(pattern, escape="\\"))
        count_stmt = select(func.count()).select_from(Upazila).where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())
        stmt = select(Upazila).where(*filters).order_by(Upazila.id.asc()).limit(limit).offset(offset)
        rows = list((await self._session.execute(stmt)).scalars().all())
        return rows, total

    async def update_upazila(
        self,
        upazila: Upazila,
        *,
        name: str,
        district_id: int,
        actor: str,
    ) -> Upazila:
        upazila.name = name
        upazila.district_id = district_id
        upazila.updated_by = actor
        await self._session.flush()
        return upazila

    async def delete_upazila(self, upazila: Upazila) -> None:
        await self._session.delete(upazila)
        await self._session.flush()

    # ── Users ──────────────────────────────────────────────────────────────

    async def create_user(
        self,
        *,
        user_id: int,
        name: str,
        role: str,
        parent_id: int | None,
        district_id: int,
        upazilas: list[Upazila],
        tenant_id: int,
        actor: str,
    ) -> HierarchyUser:
        user = HierarchyUser(
            id=user_id,
            name=name,
            role=role,
            parent_id=parent_id,
            district_id=district_id,
            tenant_id=tenant_id,
            created_by=actor,
            updated_by=actor,
        )
        user.upazilas = upazilas
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_user(self, user_id: int, *, tenant_id: int) -> HierarchyUser | None:
        stmt = select(HierarchyUser).where(
            HierarchyUser.id == user_id,
            HierarchyUser.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> HierarchyUser | None:
        """Auth lookup — id is global across tenants for SPICE parity."""
        stmt = select(HierarchyUser).where(HierarchyUser.id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_users_by_ids(self, user_ids: list[int]) -> dict[int, HierarchyUser]:
        """Batch lookup by id (global across tenants for SPICE parity)."""
        if not user_ids:
            return {}
        stmt = select(HierarchyUser).where(HierarchyUser.id.in_(user_ids))
        rows = list((await self._session.execute(stmt)).scalars().all())
        return {user.id: user for user in rows}

    async def list_users(
        self,
        *,
        tenant_id: int,
        district_id: int | None,
        role: str | None,
        parent_id: int | None,
        upazila_id: int | None,
        name_query: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[HierarchyUser], int]:
        filters = [HierarchyUser.tenant_id == tenant_id]
        if district_id is not None:
            filters.append(HierarchyUser.district_id == district_id)
        if role is not None:
            filters.append(HierarchyUser.role == role)
        if parent_id is not None:
            filters.append(HierarchyUser.parent_id == parent_id)
        if upazila_id is not None:
            filters.append(
                select(UserUpazila.user_id)
                .where(
                    UserUpazila.user_id == HierarchyUser.id,
                    UserUpazila.upazila_id == upazila_id,
                )
                .exists()
            )
        if name_query:
            pattern = f"%{_escape_ilike_pattern(name_query.strip())}%"
            filters.append(HierarchyUser.name.ilike(pattern, escape="\\"))

        count_stmt = select(func.count()).select_from(HierarchyUser).where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())
        stmt = (
            select(HierarchyUser).where(*filters).order_by(HierarchyUser.id.asc()).limit(limit).offset(offset)
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return rows, total

    async def update_user(
        self,
        user: HierarchyUser,
        *,
        name: str,
        role: str,
        parent_id: int | None,
        district_id: int,
        upazilas: list[Upazila],
        actor: str,
    ) -> HierarchyUser:
        user.name = name
        user.role = role
        user.parent_id = parent_id
        user.district_id = district_id
        user.upazilas = upazilas
        user.updated_by = actor
        await self._session.flush()
        return user

    async def delete_user(self, user: HierarchyUser) -> None:
        await self._session.delete(user)
        await self._session.flush()

    async def user_id_exists(self, user_id: int) -> bool:
        stmt = select(HierarchyUser.id).where(HierarchyUser.id == user_id).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None
