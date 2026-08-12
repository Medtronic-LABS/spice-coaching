"""Admin orchestration for districts, upazilas, and hierarchy users."""

from __future__ import annotations

from mc_contracts.errors import ErrorCode
from mc_contracts.hierarchy import (
    DistrictCreateRequest,
    DistrictListResponse,
    DistrictResponse,
    DistrictUpdateRequest,
    HierarchyUserCreateRequest,
    HierarchyUserListResponse,
    HierarchyUserResponse,
    HierarchyUserUpdateRequest,
    UpazilaCreateRequest,
    UpazilaListResponse,
    UpazilaResponse,
    UpazilaUpdateRequest,
)
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.district import District
from platform_service.db.models.hierarchy_user import HierarchyUser
from platform_service.db.models.upazila import Upazila
from platform_service.db.repositories.hierarchy_repository import HierarchyRepository
from platform_service.services.hierarchy_validator import (
    DistrictSnapshot,
    ParentSnapshot,
    UpazilaSnapshot,
    validate_hierarchy_user,
)


class HierarchyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = HierarchyRepository(session)

    # ── Districts ──────────────────────────────────────────────────────────

    async def create_district(
        self,
        body: DistrictCreateRequest,
        *,
        tenant_id: int,
        actor: str,
    ) -> DistrictResponse:
        district = await self._repo.create_district(
            name=body.name,
            tenant_id=tenant_id,
            actor=actor,
        )
        await self._session.commit()
        await self._session.refresh(district)
        return self._district_response(district)

    async def get_district(self, district_id: int, *, tenant_id: int) -> DistrictResponse:
        district = await self._repo.get_district(district_id, tenant_id=tenant_id)
        if district is None:
            raise AppError(
                ErrorCode.HIERARCHY_DISTRICT_NOT_FOUND.value,
                f"District '{district_id}' not found.",
                status=404,
            )
        return self._district_response(district)

    async def list_districts(
        self,
        *,
        tenant_id: int,
        name_query: str | None = None,
        limit: int,
        offset: int,
    ) -> DistrictListResponse:
        districts, total = await self._repo.list_districts(
            tenant_id=tenant_id,
            name_query=name_query,
            limit=limit,
            offset=offset,
        )
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        return DistrictListResponse(
            districts=[self._district_response(d) for d in districts],
            total=total,
            total_pages=total_pages,
            limit=limit,
            offset=offset,
        )

    async def update_district(
        self,
        district_id: int,
        body: DistrictUpdateRequest,
        *,
        tenant_id: int,
        actor: str,
    ) -> DistrictResponse:
        district = await self._repo.get_district(district_id, tenant_id=tenant_id)
        if district is None:
            raise AppError(
                ErrorCode.HIERARCHY_DISTRICT_NOT_FOUND.value,
                f"District '{district_id}' not found.",
                status=404,
            )
        await self._repo.update_district(district, name=body.name, actor=actor)
        await self._session.commit()
        await self._session.refresh(district)
        return self._district_response(district)

    async def delete_district(self, district_id: int, *, tenant_id: int) -> None:
        district = await self._repo.get_district(district_id, tenant_id=tenant_id)
        if district is None:
            raise AppError(
                ErrorCode.HIERARCHY_DISTRICT_NOT_FOUND.value,
                f"District '{district_id}' not found.",
                status=404,
            )
        await self._repo.delete_district(district)
        await self._session.commit()

    # ── Upazilas ───────────────────────────────────────────────────────────

    async def create_upazila(
        self,
        body: UpazilaCreateRequest,
        *,
        tenant_id: int,
        actor: str,
    ) -> UpazilaResponse:
        district = await self._repo.get_district(body.district_id, tenant_id=tenant_id)
        if district is None:
            raise AppError(
                ErrorCode.HIERARCHY_DISTRICT_NOT_FOUND.value,
                f"District '{body.district_id}' not found.",
                status=404,
            )
        upazila = await self._repo.create_upazila(
            name=body.name,
            district_id=body.district_id,
            tenant_id=tenant_id,
            actor=actor,
        )
        await self._session.commit()
        await self._session.refresh(upazila)
        return self._upazila_response(upazila)

    async def get_upazila(self, upazila_id: int, *, tenant_id: int) -> UpazilaResponse:
        upazila = await self._repo.get_upazila(upazila_id, tenant_id=tenant_id)
        if upazila is None:
            raise AppError(
                ErrorCode.HIERARCHY_UPAZILA_NOT_FOUND.value,
                f"Upazila '{upazila_id}' not found.",
                status=404,
            )
        return self._upazila_response(upazila)

    async def list_upazilas(
        self,
        *,
        tenant_id: int,
        district_id: int | None,
        name_query: str | None = None,
        limit: int,
        offset: int,
    ) -> UpazilaListResponse:
        upazilas, total = await self._repo.list_upazilas(
            tenant_id=tenant_id,
            district_id=district_id,
            name_query=name_query,
            limit=limit,
            offset=offset,
        )
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        return UpazilaListResponse(
            upazilas=[self._upazila_response(u) for u in upazilas],
            total=total,
            total_pages=total_pages,
            limit=limit,
            offset=offset,
        )

    async def update_upazila(
        self,
        upazila_id: int,
        body: UpazilaUpdateRequest,
        *,
        tenant_id: int,
        actor: str,
    ) -> UpazilaResponse:
        upazila = await self._repo.get_upazila(upazila_id, tenant_id=tenant_id)
        if upazila is None:
            raise AppError(
                ErrorCode.HIERARCHY_UPAZILA_NOT_FOUND.value,
                f"Upazila '{upazila_id}' not found.",
                status=404,
            )
        district = await self._repo.get_district(body.district_id, tenant_id=tenant_id)
        if district is None:
            raise AppError(
                ErrorCode.HIERARCHY_DISTRICT_NOT_FOUND.value,
                f"District '{body.district_id}' not found.",
                status=404,
            )
        await self._repo.update_upazila(
            upazila,
            name=body.name,
            district_id=body.district_id,
            actor=actor,
        )
        await self._session.commit()
        await self._session.refresh(upazila)
        return self._upazila_response(upazila)

    async def delete_upazila(self, upazila_id: int, *, tenant_id: int) -> None:
        upazila = await self._repo.get_upazila(upazila_id, tenant_id=tenant_id)
        if upazila is None:
            raise AppError(
                ErrorCode.HIERARCHY_UPAZILA_NOT_FOUND.value,
                f"Upazila '{upazila_id}' not found.",
                status=404,
            )
        await self._repo.delete_upazila(upazila)
        await self._session.commit()

    # ── Users ──────────────────────────────────────────────────────────────

    async def create_user(
        self,
        body: HierarchyUserCreateRequest,
        *,
        tenant_id: int,
        actor: str,
    ) -> HierarchyUserResponse:
        if await self._repo.user_id_exists(body.id):
            raise AppError(
                ErrorCode.HIERARCHY_USER_CONFLICT.value,
                f"Hierarchy user id '{body.id}' already exists.",
                status=409,
            )
        upazila_objs = await self._repo.get_upazilas_by_ids(body.upazila_ids, tenant_id=tenant_id)
        if len(upazila_objs) != len(set(body.upazila_ids)):
            raise AppError(
                ErrorCode.HIERARCHY_UPAZILA_NOT_FOUND.value,
                "One or more specified upazila_ids were not found.",
                status=404,
            )
        await self._validate_user_write(
            role=body.role.value,
            parent_id=body.parent_id,
            district_id=body.district_id,
            upazila_ids=body.upazila_ids,
            upazila_objs=upazila_objs,
            tenant_id=tenant_id,
        )
        user = await self._repo.create_user(
            user_id=body.id,
            name=body.name,
            role=body.role.value,
            parent_id=body.parent_id,
            district_id=body.district_id,
            upazilas=upazila_objs,
            tenant_id=tenant_id,
            actor=actor,
        )
        await self._session.commit()
        await self._session.refresh(user)
        return self._user_response(user)

    async def get_user(self, user_id: int, *, tenant_id: int) -> HierarchyUserResponse:
        user = await self.find_user(user_id, tenant_id=tenant_id)
        if user is None:
            raise AppError(
                ErrorCode.HIERARCHY_USER_NOT_FOUND.value,
                f"Hierarchy user '{user_id}' not found.",
                status=404,
            )
        return user

    async def find_user(self, user_id: int, *, tenant_id: int) -> HierarchyUserResponse | None:
        user = await self._repo.get_user(user_id, tenant_id=tenant_id)
        if user is None:
            return None
        return self._user_response(user)

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
    ) -> HierarchyUserListResponse:
        users, total = await self._repo.list_users(
            tenant_id=tenant_id,
            district_id=district_id,
            role=role,
            parent_id=parent_id,
            upazila_id=upazila_id,
            name_query=name_query,
            limit=limit,
            offset=offset,
        )
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        return HierarchyUserListResponse(
            users=[self._user_response(u) for u in users],
            total=total,
            total_pages=total_pages,
            limit=limit,
            offset=offset,
        )

    async def list_all_users(
        self,
        *,
        tenant_id: int,
        district_id: int | None = None,
        role: str | None = None,
        parent_id: int | None = None,
        upazila_id: int | None = None,
        page_size: int = 200,
    ) -> list[HierarchyUserResponse]:
        """Return every matching hierarchy user by paging through ``list_users``."""
        page_size = min(max(page_size, 1), 200)
        collected: list[HierarchyUserResponse] = []
        offset = 0
        while True:
            page = await self.list_users(
                tenant_id=tenant_id,
                district_id=district_id,
                role=role,
                parent_id=parent_id,
                upazila_id=upazila_id,
                limit=page_size,
                offset=offset,
            )
            collected.extend(page.users)
            if not page.users or len(collected) >= page.total:
                break
            offset += page_size
        return collected

    async def district_names_by_ids(
        self,
        district_ids: set[int],
        *,
        tenant_id: int,
    ) -> dict[int, str]:
        districts = await self._repo.get_districts_by_ids(district_ids, tenant_id=tenant_id)
        return {d_id: d.name for d_id, d in districts.items()}

    async def update_user(
        self,
        user_id: int,
        body: HierarchyUserUpdateRequest,
        *,
        tenant_id: int,
        actor: str,
    ) -> HierarchyUserResponse:
        user = await self._repo.get_user(user_id, tenant_id=tenant_id)
        if user is None:
            raise AppError(
                ErrorCode.HIERARCHY_USER_NOT_FOUND.value,
                f"Hierarchy user '{user_id}' not found.",
                status=404,
            )
        if body.parent_id is not None and body.parent_id == user_id:
            raise AppError(
                ErrorCode.HIERARCHY_PARENT_INVALID.value,
                "User cannot be their own parent.",
                status=400,
            )
        upazila_objs = await self._repo.get_upazilas_by_ids(body.upazila_ids, tenant_id=tenant_id)
        if len(upazila_objs) != len(set(body.upazila_ids)):
            raise AppError(
                ErrorCode.HIERARCHY_UPAZILA_NOT_FOUND.value,
                "One or more specified upazila_ids were not found.",
                status=404,
            )
        await self._validate_user_write(
            role=body.role.value,
            parent_id=body.parent_id,
            district_id=body.district_id,
            upazila_ids=body.upazila_ids,
            upazila_objs=upazila_objs,
            tenant_id=tenant_id,
        )
        await self._repo.update_user(
            user,
            name=body.name,
            role=body.role.value,
            parent_id=body.parent_id,
            district_id=body.district_id,
            upazilas=upazila_objs,
            actor=actor,
        )
        await self._session.commit()
        await self._session.refresh(user)
        return self._user_response(user)

    async def delete_user(self, user_id: int, *, tenant_id: int) -> None:
        user = await self._repo.get_user(user_id, tenant_id=tenant_id)
        if user is None:
            raise AppError(
                ErrorCode.HIERARCHY_USER_NOT_FOUND.value,
                f"Hierarchy user '{user_id}' not found.",
                status=404,
            )
        await self._repo.delete_user(user)
        await self._session.commit()

    async def _validate_user_write(
        self,
        *,
        role: str,
        parent_id: int | None,
        district_id: int,
        upazila_ids: list[int],
        upazila_objs: list[Upazila],
        tenant_id: int,
    ) -> None:
        district = await self._repo.get_district(district_id, tenant_id=tenant_id)
        district_snap = (
            None if district is None else DistrictSnapshot(id=district.id, tenant_id=district.tenant_id)
        )
        parent_snap: ParentSnapshot | None = None
        if parent_id is not None:
            parent = await self._repo.get_user(parent_id, tenant_id=tenant_id)
            if parent is not None:
                parent_snap = ParentSnapshot(
                    id=parent.id,
                    role=parent.role,
                    district_id=parent.district_id,
                    tenant_id=parent.tenant_id,
                    upazila_ids={u.id for u in parent.upazilas},
                )
        upazilas_map = {
            u.id: UpazilaSnapshot(id=u.id, district_id=u.district_id, tenant_id=u.tenant_id)
            for u in upazila_objs
        }
        validate_hierarchy_user(
            role=role,
            parent_id=parent_id,
            district_id=district_id,
            tenant_id=tenant_id,
            upazila_ids=upazila_ids,
            parent=parent_snap,
            district=district_snap,
            upazilas_map=upazilas_map,
        )

    @staticmethod
    def _district_response(district: District) -> DistrictResponse:
        return DistrictResponse(
            id=district.id,
            name=district.name,
            tenant_id=district.tenant_id,
            created_at=district.created_at,
            updated_at=district.updated_at,
            created_by=district.created_by,
            updated_by=district.updated_by,
        )

    @staticmethod
    def _upazila_response(upazila: Upazila) -> UpazilaResponse:
        return UpazilaResponse(
            id=upazila.id,
            name=upazila.name,
            district_id=upazila.district_id,
            tenant_id=upazila.tenant_id,
            created_at=upazila.created_at,
            updated_at=upazila.updated_at,
            created_by=upazila.created_by,
            updated_by=upazila.updated_by,
        )

    @classmethod
    def _user_response(cls, user: HierarchyUser) -> HierarchyUserResponse:
        return HierarchyUserResponse(
            id=user.id,
            name=user.name,
            role=user.role,  # type: ignore[arg-type]
            parent_id=user.parent_id,
            district_id=user.district_id,
            upazilas=[cls._upazila_response(u) for u in user.upazilas],
            tenant_id=user.tenant_id,
            created_at=user.created_at,
            updated_at=user.updated_at,
            created_by=user.created_by,
            updated_by=user.updated_by,
        )
