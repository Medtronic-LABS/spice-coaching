"""Repository for division, district, upazila, and hierarchy users tables."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.district import District
from platform_service.db.models.division import Division
from platform_service.db.models.hierarchy_user import ROLE_SUPER_ADMIN, HierarchyUser
from platform_service.db.models.role import Role
from platform_service.db.models.upazila import Upazila
from platform_service.db.models.user_upazila import UserUpazila


def _escape_ilike_pattern(value: str) -> str:
    """Escape SQL ``LIKE``/``ILIKE`` wildcards in user input."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class HierarchyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Divisions ──────────────────────────────────────────────────────────

    async def create_division(
        self,
        *,
        name: str,
        tenant_id: int,
        actor: int | None,
    ) -> Division:
        division = Division(
            name=name,
            tenant_id=tenant_id,
            created_by=actor,
            updated_by=actor,
        )
        self._session.add(division)
        await self._session.flush()
        return division

    async def get_division(self, division_id: int, *, tenant_id: int) -> Division | None:
        stmt = select(Division).where(
            Division.id == division_id,
            Division.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_divisions_by_ids(
        self,
        division_ids: set[int],
        *,
        tenant_id: int,
    ) -> dict[int, Division]:
        if not division_ids:
            return {}
        stmt = select(Division).where(
            Division.tenant_id == tenant_id,
            Division.id.in_(division_ids),
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return {d.id: d for d in rows}

    async def list_divisions(
        self,
        *,
        tenant_id: int,
        name_query: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Division], int]:
        filters = [Division.tenant_id == tenant_id]
        if name_query:
            pattern = f"%{_escape_ilike_pattern(name_query.strip())}%"
            filters.append(Division.name.ilike(pattern, escape="\\"))
        count_stmt = select(func.count()).select_from(Division).where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())
        stmt = select(Division).where(*filters).order_by(Division.id.asc()).limit(limit).offset(offset)
        rows = list((await self._session.execute(stmt)).scalars().all())
        return rows, total

    async def list_all_divisions(self, *, tenant_id: int) -> list[Division]:
        stmt = select(Division).where(Division.tenant_id == tenant_id).order_by(Division.id.asc())
        return list((await self._session.execute(stmt)).scalars().all())

    async def update_division(
        self,
        division: Division,
        *,
        name: str,
        actor: int | None,
    ) -> Division:
        division.name = name
        division.updated_by = actor
        await self._session.flush()
        return division

    async def delete_division(self, division: Division) -> None:
        await self._session.delete(division)
        await self._session.flush()

    # ── Districts ──────────────────────────────────────────────────────────

    async def create_district(
        self,
        *,
        name: str,
        division_id: int | None,
        tenant_id: int,
        actor: int | None,
    ) -> District:
        district = District(
            name=name,
            division_id=division_id,
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
        division_id: int | None = None,
        name_query: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[District], int]:
        filters = [District.tenant_id == tenant_id]
        if division_id is not None:
            filters.append(District.division_id == division_id)
        if name_query:
            pattern = f"%{_escape_ilike_pattern(name_query.strip())}%"
            filters.append(District.name.ilike(pattern, escape="\\"))
        count_stmt = select(func.count()).select_from(District).where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())
        stmt = select(District).where(*filters).order_by(District.id.asc()).limit(limit).offset(offset)
        rows = list((await self._session.execute(stmt)).scalars().all())
        return rows, total

    async def list_all_districts(self, *, tenant_id: int) -> list[District]:
        stmt = select(District).where(District.tenant_id == tenant_id).order_by(District.id.asc())
        return list((await self._session.execute(stmt)).scalars().all())

    async def update_district(
        self,
        district: District,
        *,
        name: str,
        division_id: int | None,
        actor: int | None,
    ) -> District:
        district.name = name
        district.division_id = division_id
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
        actor: int | None,
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

    async def list_all_upazilas(self, *, tenant_id: int) -> list[Upazila]:
        stmt = select(Upazila).where(Upazila.tenant_id == tenant_id).order_by(Upazila.id.asc())
        return list((await self._session.execute(stmt)).scalars().all())

    async def update_upazila(
        self,
        upazila: Upazila,
        *,
        name: str,
        district_id: int,
        actor: int | None,
    ) -> Upazila:
        upazila.name = name
        upazila.district_id = district_id
        upazila.updated_by = actor
        await self._session.flush()
        return upazila

    async def delete_upazila(self, upazila: Upazila) -> None:
        await self._session.delete(upazila)
        await self._session.flush()

    # ── Roles ──────────────────────────────────────────────────────────────

    async def get_role_by_code(self, code: str) -> Role | None:
        stmt = select(Role).where(Role.code == code)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def require_role_by_code(self, code: str) -> Role:
        role = await self.get_role_by_code(code)
        if role is None:
            msg = f"Unknown hierarchy role code: {code}"
            raise ValueError(msg)
        return role

    # ── Users ──────────────────────────────────────────────────────────────

    async def create_user(
        self,
        *,
        user_id: int,
        name: str,
        role: str,
        parent_id: int | None,
        district_id: int | None,
        upazilas: list[Upazila],
        tenant_id: int,
        actor: int | None,
    ) -> HierarchyUser:
        role_row = await self.require_role_by_code(role)
        user = HierarchyUser(
            id=user_id,
            name=name,
            role_id=role_row.id,
            parent_id=parent_id,
            district_id=district_id,
            tenant_id=tenant_id,
            created_by=actor,
            updated_by=actor,
        )
        user.role_row = role_row
        user.upazilas = upazilas
        self._session.add(user)
        await self._session.flush()
        return user

    async def ensure_super_admin_user(
        self,
        *,
        user_id: int,
        name: str,
        tenant_id: int,
    ) -> HierarchyUser:
        """Insert a root SUPER_ADMIN with null district if missing; return the row."""
        existing = await self.get_user_by_id(user_id)
        if existing is not None:
            return existing
        return await self.create_user(
            user_id=user_id,
            name=name,
            role=ROLE_SUPER_ADMIN,
            parent_id=None,
            district_id=None,
            upazilas=[],
            tenant_id=tenant_id,
            actor=user_id,
        )

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
        division_id: int | None,
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
        if division_id is not None:
            filters.append(
                select(District.id)
                .where(
                    District.id == HierarchyUser.district_id,
                    District.division_id == division_id,
                    District.tenant_id == tenant_id,
                )
                .exists()
            )
        if role is not None:
            filters.append(
                select(Role.id).where(Role.id == HierarchyUser.role_id, Role.code == role).exists()
            )
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

    async def list_all_users(self, *, tenant_id: int) -> list[HierarchyUser]:
        stmt = (
            select(HierarchyUser).where(HierarchyUser.tenant_id == tenant_id).order_by(HierarchyUser.id.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def update_user(
        self,
        user: HierarchyUser,
        *,
        name: str,
        role: str,
        parent_id: int | None,
        district_id: int,
        upazilas: list[Upazila],
        actor: int | None,
    ) -> HierarchyUser:
        role_row = await self.require_role_by_code(role)
        user.name = name
        user.role_id = role_row.id
        user.role_row = role_row
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
