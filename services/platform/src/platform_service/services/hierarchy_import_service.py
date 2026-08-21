"""Atomically mirror tenant hierarchy from a validated desired spreadsheet graph."""

from __future__ import annotations

import logging

from mc_contracts.errors import ErrorCode
from mc_contracts.hierarchy import HierarchyImportCounts, HierarchyImportResponse
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.district import District
from platform_service.db.models.division import Division
from platform_service.db.models.hierarchy_user import (
    HIERARCHY_ROLES,
    ROLE_AREA_MANAGER,
    ROLE_PO,
    ROLE_SHASTIYA_KORMI,
    HierarchyUser,
)
from platform_service.db.models.upazila import Upazila
from platform_service.db.repositories.hierarchy_repository import HierarchyRepository
from platform_service.services.hierarchy_import_parser import (
    DesiredHierarchy,
    DesiredUser,
    parse_hierarchy_import_file,
)
from platform_service.services.hierarchy_validator import (
    DistrictSnapshot,
    ParentSnapshot,
    UpazilaSnapshot,
    validate_hierarchy_user,
)

logger = logging.getLogger(__name__)

_ROLE_APPLY_ORDER = (ROLE_AREA_MANAGER, ROLE_PO, ROLE_SHASTIYA_KORMI)
_ROLE_DELETE_ORDER = (ROLE_SHASTIYA_KORMI, ROLE_PO, ROLE_AREA_MANAGER)


def _norm(value: str) -> str:
    return value.strip().casefold()


class HierarchyImportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = HierarchyRepository(session)

    async def import_file(
        self,
        *,
        filename: str | None,
        data: bytes,
        tenant_id: int,
        actor: int | None,
    ) -> HierarchyImportResponse:
        desired = parse_hierarchy_import_file(filename=filename, data=data)
        response = await self._reconcile(desired, tenant_id=tenant_id, actor=actor)
        await self._session.commit()
        logger.info(
            "hierarchy import completed tenant_id=%s actor=%s filename=%s "
            "divisions=%s districts=%s upazilas=%s users=%s",
            tenant_id,
            actor,
            filename,
            response.divisions.model_dump(),
            response.districts.model_dump(),
            response.upazilas.model_dump(),
            response.users.model_dump(),
        )
        return response

    async def _reconcile(
        self,
        desired: DesiredHierarchy,
        *,
        tenant_id: int,
        actor: int | None,
    ) -> HierarchyImportResponse:
        division_counts = HierarchyImportCounts()
        district_counts = HierarchyImportCounts()
        upazila_counts = HierarchyImportCounts()
        user_counts = HierarchyImportCounts()

        divisions_by_key, division_id_by_key = await self._upsert_divisions(
            desired,
            tenant_id=tenant_id,
            actor=actor,
            counts=division_counts,
        )
        districts_by_key, district_id_by_key = await self._upsert_districts(
            desired,
            division_id_by_key=division_id_by_key,
            tenant_id=tenant_id,
            actor=actor,
            counts=district_counts,
        )
        upazilas_by_key = await self._upsert_upazilas(
            desired,
            district_id_by_key=district_id_by_key,
            tenant_id=tenant_id,
            actor=actor,
            counts=upazila_counts,
        )

        existing_users = await self._repo.list_all_users(tenant_id=tenant_id)
        users_by_id = {user.id: user for user in existing_users}

        for role in _ROLE_APPLY_ORDER:
            for desired_user in desired.users.values():
                if desired_user.role != role:
                    continue
                await self._upsert_user(
                    desired_user,
                    users_by_id=users_by_id,
                    districts_by_key=districts_by_key,
                    upazilas_by_key=upazilas_by_key,
                    tenant_id=tenant_id,
                    actor=actor,
                    counts=user_counts,
                )

        await self._delete_absent_users(
            desired_ids=set(desired.users),
            users_by_id=users_by_id,
            counts=user_counts,
        )
        await self._delete_absent_geo(
            desired,
            divisions_by_key=divisions_by_key,
            districts_by_key=districts_by_key,
            upazilas_by_key=upazilas_by_key,
            remaining_users=list(users_by_id.values()),
            division_counts=division_counts,
            district_counts=district_counts,
            upazila_counts=upazila_counts,
        )

        return HierarchyImportResponse(
            divisions=division_counts,
            districts=district_counts,
            upazilas=upazila_counts,
            users=user_counts,
        )

    async def _upsert_divisions(
        self,
        desired: DesiredHierarchy,
        *,
        tenant_id: int,
        actor: int | None,
        counts: HierarchyImportCounts,
    ) -> tuple[dict[str, Division], dict[str, int]]:
        existing = await self._repo.list_all_divisions(tenant_id=tenant_id)
        by_key = {_norm(d.name): d for d in existing}
        id_by_key: dict[str, int] = {}
        for key, display_name in desired.division_names.items():
            current = by_key.get(key)
            if current is None:
                created = await self._repo.create_division(
                    name=display_name,
                    tenant_id=tenant_id,
                    actor=actor,
                )
                by_key[key] = created
                id_by_key[key] = created.id
                counts.created += 1
            else:
                id_by_key[key] = current.id
        return by_key, id_by_key

    async def _upsert_districts(
        self,
        desired: DesiredHierarchy,
        *,
        division_id_by_key: dict[str, int],
        tenant_id: int,
        actor: int | None,
        counts: HierarchyImportCounts,
    ) -> tuple[dict[tuple[str, str], District], dict[tuple[str, str], int]]:
        existing = await self._repo.list_all_districts(tenant_id=tenant_id)
        divisions = await self._repo.list_all_divisions(tenant_id=tenant_id)
        division_key_by_id = {d.id: _norm(d.name) for d in divisions}

        by_key: dict[tuple[str, str], District] = {}
        for district in existing:
            if district.division_id is None:
                continue
            div_key = division_key_by_id.get(district.division_id)
            if div_key is None:
                continue
            by_key[(div_key, _norm(district.name))] = district

        id_by_key: dict[tuple[str, str], int] = {}
        for key, display_name in desired.district_names.items():
            div_key, _district_key = key
            current = by_key.get(key)
            division_id = division_id_by_key[div_key]
            if current is None:
                created = await self._repo.create_district(
                    name=display_name,
                    division_id=division_id,
                    tenant_id=tenant_id,
                    actor=actor,
                )
                by_key[key] = created
                id_by_key[key] = created.id
                counts.created += 1
            else:
                if current.division_id != division_id:
                    await self._repo.update_district(
                        current,
                        name=current.name,
                        division_id=division_id,
                        actor=actor,
                    )
                    counts.updated += 1
                id_by_key[key] = current.id
        return by_key, id_by_key

    async def _upsert_upazilas(
        self,
        desired: DesiredHierarchy,
        *,
        district_id_by_key: dict[tuple[str, str], int],
        tenant_id: int,
        actor: int | None,
        counts: HierarchyImportCounts,
    ) -> dict[tuple[str, str, str], Upazila]:
        existing = await self._repo.list_all_upazilas(tenant_id=tenant_id)
        districts = await self._repo.list_all_districts(tenant_id=tenant_id)
        divisions = await self._repo.list_all_divisions(tenant_id=tenant_id)
        division_key_by_id = {d.id: _norm(d.name) for d in divisions}
        district_key_by_id: dict[int, tuple[str, str]] = {}
        for district in districts:
            if district.division_id is None:
                continue
            div_key = division_key_by_id.get(district.division_id)
            if div_key is None:
                continue
            district_key_by_id[district.id] = (div_key, _norm(district.name))

        by_key: dict[tuple[str, str, str], Upazila] = {}
        for upazila in existing:
            dkey = district_key_by_id.get(upazila.district_id)
            if dkey is None:
                continue
            by_key[(*dkey, _norm(upazila.name))] = upazila

        for key, display_name in desired.upazila_names.items():
            current = by_key.get(key)
            district_id = district_id_by_key[key[:2]]
            if current is None:
                created = await self._repo.create_upazila(
                    name=display_name,
                    district_id=district_id,
                    tenant_id=tenant_id,
                    actor=actor,
                )
                by_key[key] = created
                counts.created += 1
            elif current.district_id != district_id:
                await self._repo.update_upazila(
                    current,
                    name=current.name,
                    district_id=district_id,
                    actor=actor,
                )
                counts.updated += 1
        return by_key

    async def _upsert_user(
        self,
        desired_user: DesiredUser,
        *,
        users_by_id: dict[int, HierarchyUser],
        districts_by_key: dict[tuple[str, str], District],
        upazilas_by_key: dict[tuple[str, str, str], Upazila],
        tenant_id: int,
        actor: int | None,
        counts: HierarchyImportCounts,
    ) -> None:
        district_key = (_norm(desired_user.division), _norm(desired_user.district))
        district = districts_by_key[district_key]
        upazila_objs = [
            upazilas_by_key[(district_key[0], district_key[1], ukey)]
            for ukey in sorted(desired_user.upazila_keys)
        ]
        upazila_ids = [u.id for u in upazila_objs]
        upazilas_map = {
            u.id: UpazilaSnapshot(id=u.id, district_id=u.district_id, tenant_id=u.tenant_id)
            for u in upazila_objs
        }

        parent: ParentSnapshot | None = None
        if desired_user.parent_id is not None:
            parent_user = users_by_id[desired_user.parent_id]
            parent = ParentSnapshot(
                id=parent_user.id,
                role=parent_user.role,
                district_id=parent_user.district_id,
                tenant_id=parent_user.tenant_id,
                upazila_ids={u.id for u in parent_user.upazilas},
            )

        validate_hierarchy_user(
            role=desired_user.role,
            parent_id=desired_user.parent_id,
            district_id=district.id,
            tenant_id=tenant_id,
            upazila_ids=upazila_ids,
            parent=parent,
            district=DistrictSnapshot(id=district.id, tenant_id=district.tenant_id),
            upazilas_map=upazilas_map,
        )

        existing = users_by_id.get(desired_user.user_id)
        if existing is None:
            if await self._repo.user_id_exists(desired_user.user_id):
                raise AppError(
                    ErrorCode.HIERARCHY_USER_CONFLICT.value,
                    f"Hierarchy user id {desired_user.user_id} already exists.",
                    status=409,
                )
            created = await self._repo.create_user(
                user_id=desired_user.user_id,
                name=desired_user.name,
                role=desired_user.role,
                parent_id=desired_user.parent_id,
                district_id=district.id,
                upazilas=upazila_objs,
                tenant_id=tenant_id,
                actor=actor,
            )
            users_by_id[created.id] = created
            counts.created += 1
            return

        needs_update = (
            existing.name != desired_user.name
            or existing.role != desired_user.role
            or existing.parent_id != desired_user.parent_id
            or existing.district_id != district.id
            or {u.id for u in existing.upazilas} != set(upazila_ids)
        )
        if needs_update:
            updated = await self._repo.update_user(
                existing,
                name=desired_user.name,
                role=desired_user.role,
                parent_id=desired_user.parent_id,
                district_id=district.id,
                upazilas=upazila_objs,
                actor=actor,
            )
            users_by_id[updated.id] = updated
            counts.updated += 1

    async def _delete_absent_users(
        self,
        *,
        desired_ids: set[int],
        users_by_id: dict[int, HierarchyUser],
        counts: HierarchyImportCounts,
    ) -> None:
        for role in _ROLE_DELETE_ORDER:
            to_delete = [
                user
                for user in list(users_by_id.values())
                if user.role in HIERARCHY_ROLES and user.role == role and user.id not in desired_ids
            ]
            for user in to_delete:
                await self._repo.delete_user(user)
                users_by_id.pop(user.id, None)
                counts.deleted += 1

    async def _delete_absent_geo(
        self,
        desired: DesiredHierarchy,
        *,
        divisions_by_key: dict[str, Division],
        districts_by_key: dict[tuple[str, str], District],
        upazilas_by_key: dict[tuple[str, str, str], Upazila],
        remaining_users: list[HierarchyUser],
        division_counts: HierarchyImportCounts,
        district_counts: HierarchyImportCounts,
        upazila_counts: HierarchyImportCounts,
    ) -> None:
        """Delete geo missing from the file, but keep rows still referenced by retained users."""
        retained_district_ids = {user.district_id for user in remaining_users}
        retained_upazila_ids = {u.id for user in remaining_users for u in user.upazilas}
        retained_division_ids = {
            district.division_id
            for district in districts_by_key.values()
            if district.id in retained_district_ids and district.division_id is not None
        }

        desired_upazila_keys = set(desired.upazila_names)
        for key, upazila in list(upazilas_by_key.items()):
            if key in desired_upazila_keys:
                continue
            if upazila.id in retained_upazila_ids:
                continue
            await self._repo.delete_upazila(upazila)
            upazilas_by_key.pop(key, None)
            upazila_counts.deleted += 1

        desired_district_keys = set(desired.district_names)
        for key, district in list(districts_by_key.items()):
            if key in desired_district_keys:
                continue
            if district.id in retained_district_ids:
                continue
            await self._repo.delete_district(district)
            districts_by_key.pop(key, None)
            district_counts.deleted += 1

        desired_division_keys = set(desired.division_names)
        for key, division in list(divisions_by_key.items()):
            if key in desired_division_keys:
                continue
            if division.id in retained_division_ids:
                continue
            await self._repo.delete_division(division)
            divisions_by_key.pop(key, None)
            division_counts.deleted += 1
