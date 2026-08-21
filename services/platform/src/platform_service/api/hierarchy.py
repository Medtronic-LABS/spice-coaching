"""Admin division, district, upazila, and hierarchy-user endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from mc_contracts.enums import HierarchyRole
from mc_contracts.hierarchy import (
    DistrictCreateRequest,
    DistrictListResponse,
    DistrictResponse,
    DistrictUpdateRequest,
    DivisionCreateRequest,
    DivisionListResponse,
    DivisionResponse,
    DivisionUpdateRequest,
    HierarchyImportResponse,
    HierarchyUserCreateRequest,
    HierarchyUserListResponse,
    HierarchyUserResponse,
    HierarchyUserUpdateRequest,
    UpazilaCreateRequest,
    UpazilaListResponse,
    UpazilaResponse,
    UpazilaUpdateRequest,
)
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_user import get_selected_tenant_id, resolve_spice_user_id
from platform_service.deps import get_db
from platform_service.services.hierarchy_import_service import HierarchyImportService
from platform_service.services.hierarchy_service import HierarchyService

router = APIRouter(prefix="/admin", tags=["admin-hierarchy"])


# ── Divisions ──────────────────────────────────────────────────────────────


@router.post("/divisions", response_model=DivisionResponse, status_code=201)
async def create_division(
    request: Request,
    body: DivisionCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> DivisionResponse:
    return await HierarchyService(session).create_division(
        body,
        tenant_id=get_selected_tenant_id(request),
        actor=resolve_spice_user_id(request),
    )


@router.get("/divisions", response_model=DivisionListResponse)
async def list_divisions(
    request: Request,
    q: str | None = Query(None, description="Case-insensitive substring match on name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> DivisionListResponse:
    name_query = q.strip() if q and q.strip() else None
    return await HierarchyService(session).list_divisions(
        tenant_id=get_selected_tenant_id(request),
        name_query=name_query,
        limit=limit,
        offset=offset,
    )


@router.get("/divisions/{division_id}", response_model=DivisionResponse)
async def get_division(
    request: Request,
    division_id: int,
    session: AsyncSession = Depends(get_db),
) -> DivisionResponse:
    return await HierarchyService(session).get_division(
        division_id,
        tenant_id=get_selected_tenant_id(request),
    )


@router.put("/divisions/{division_id}", response_model=DivisionResponse)
async def update_division(
    request: Request,
    division_id: int,
    body: DivisionUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> DivisionResponse:
    return await HierarchyService(session).update_division(
        division_id,
        body,
        tenant_id=get_selected_tenant_id(request),
        actor=resolve_spice_user_id(request),
    )


@router.delete("/divisions/{division_id}", status_code=204)
async def delete_division(
    request: Request,
    division_id: int,
    session: AsyncSession = Depends(get_db),
) -> Response:
    await HierarchyService(session).delete_division(
        division_id,
        tenant_id=get_selected_tenant_id(request),
    )
    return Response(status_code=204)


# ── Districts ──────────────────────────────────────────────────────────────


@router.post("/districts", response_model=DistrictResponse, status_code=201)
async def create_district(
    request: Request,
    body: DistrictCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> DistrictResponse:
    return await HierarchyService(session).create_district(
        body,
        tenant_id=get_selected_tenant_id(request),
        actor=resolve_spice_user_id(request),
    )


@router.get("/districts", response_model=DistrictListResponse)
async def list_districts(
    request: Request,
    division_id: int | None = Query(None),
    q: str | None = Query(None, description="Case-insensitive substring match on name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> DistrictListResponse:
    name_query = q.strip() if q and q.strip() else None
    return await HierarchyService(session).list_districts(
        tenant_id=get_selected_tenant_id(request),
        division_id=division_id,
        name_query=name_query,
        limit=limit,
        offset=offset,
    )


@router.get("/districts/{district_id}", response_model=DistrictResponse)
async def get_district(
    request: Request,
    district_id: int,
    session: AsyncSession = Depends(get_db),
) -> DistrictResponse:
    return await HierarchyService(session).get_district(
        district_id,
        tenant_id=get_selected_tenant_id(request),
    )


@router.put("/districts/{district_id}", response_model=DistrictResponse)
async def update_district(
    request: Request,
    district_id: int,
    body: DistrictUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> DistrictResponse:
    return await HierarchyService(session).update_district(
        district_id,
        body,
        tenant_id=get_selected_tenant_id(request),
        actor=resolve_spice_user_id(request),
    )


@router.delete("/districts/{district_id}", status_code=204)
async def delete_district(
    request: Request,
    district_id: int,
    session: AsyncSession = Depends(get_db),
) -> Response:
    await HierarchyService(session).delete_district(
        district_id,
        tenant_id=get_selected_tenant_id(request),
    )
    return Response(status_code=204)


# ── Upazilas ───────────────────────────────────────────────────────────────


@router.post("/upazilas", response_model=UpazilaResponse, status_code=201)
async def create_upazila(
    request: Request,
    body: UpazilaCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> UpazilaResponse:
    return await HierarchyService(session).create_upazila(
        body,
        tenant_id=get_selected_tenant_id(request),
        actor=resolve_spice_user_id(request),
    )


@router.get("/upazilas", response_model=UpazilaListResponse)
async def list_upazilas(
    request: Request,
    district_id: int | None = Query(None),
    q: str | None = Query(None, description="Case-insensitive substring match on name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> UpazilaListResponse:
    name_query = q.strip() if q and q.strip() else None
    return await HierarchyService(session).list_upazilas(
        tenant_id=get_selected_tenant_id(request),
        district_id=district_id,
        name_query=name_query,
        limit=limit,
        offset=offset,
    )


@router.get("/upazilas/{upazila_id}", response_model=UpazilaResponse)
async def get_upazila(
    request: Request,
    upazila_id: int,
    session: AsyncSession = Depends(get_db),
) -> UpazilaResponse:
    return await HierarchyService(session).get_upazila(
        upazila_id,
        tenant_id=get_selected_tenant_id(request),
    )


@router.put("/upazilas/{upazila_id}", response_model=UpazilaResponse)
async def update_upazila(
    request: Request,
    upazila_id: int,
    body: UpazilaUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> UpazilaResponse:
    return await HierarchyService(session).update_upazila(
        upazila_id,
        body,
        tenant_id=get_selected_tenant_id(request),
        actor=resolve_spice_user_id(request),
    )


@router.delete("/upazilas/{upazila_id}", status_code=204)
async def delete_upazila(
    request: Request,
    upazila_id: int,
    session: AsyncSession = Depends(get_db),
) -> Response:
    await HierarchyService(session).delete_upazila(
        upazila_id,
        tenant_id=get_selected_tenant_id(request),
    )
    return Response(status_code=204)


# ── Users ──────────────────────────────────────────────────────────────────


@router.post("/hierarchy/import", response_model=HierarchyImportResponse)
async def import_hierarchy(
    request: Request,
    file: UploadFile = File(..., description="Hierarchy CSV or XLSX org-chart file"),
    session: AsyncSession = Depends(get_db),
) -> HierarchyImportResponse:
    """Mirror tenant Division/District/Upazila and AM→PO→SK rows from a spreadsheet."""
    data = await file.read()
    return await HierarchyImportService(session).import_file(
        filename=file.filename,
        data=data,
        tenant_id=get_selected_tenant_id(request),
        actor=resolve_spice_user_id(request),
    )


@router.post("/hierarchy/users", response_model=HierarchyUserResponse, status_code=201)
async def create_hierarchy_user(
    request: Request,
    body: HierarchyUserCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> HierarchyUserResponse:
    return await HierarchyService(session).create_user(
        body,
        tenant_id=get_selected_tenant_id(request),
        actor=resolve_spice_user_id(request),
    )


@router.get("/hierarchy/users", response_model=HierarchyUserListResponse)
async def list_hierarchy_users(
    request: Request,
    district_id: int | None = Query(None),
    division_id: int | None = Query(None),
    role: HierarchyRole | None = Query(None),
    parent_id: int | None = Query(None),
    upazila_id: int | None = Query(None),
    q: str | None = Query(None, description="Case-insensitive substring match on name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> HierarchyUserListResponse:
    name_query = q.strip() if q and q.strip() else None
    return await HierarchyService(session).list_users(
        tenant_id=get_selected_tenant_id(request),
        district_id=district_id,
        division_id=division_id,
        role=role.value if role is not None else None,
        parent_id=parent_id,
        upazila_id=upazila_id,
        name_query=name_query,
        limit=limit,
        offset=offset,
    )


@router.get("/hierarchy/users/{user_id}", response_model=HierarchyUserResponse)
async def get_hierarchy_user(
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_db),
) -> HierarchyUserResponse:
    return await HierarchyService(session).get_user(
        user_id,
        tenant_id=get_selected_tenant_id(request),
    )


@router.put("/hierarchy/users/{user_id}", response_model=HierarchyUserResponse)
async def update_hierarchy_user(
    request: Request,
    user_id: int,
    body: HierarchyUserUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> HierarchyUserResponse:
    return await HierarchyService(session).update_user(
        user_id,
        body,
        tenant_id=get_selected_tenant_id(request),
        actor=resolve_spice_user_id(request),
    )


@router.delete("/hierarchy/users/{user_id}", status_code=204)
async def delete_hierarchy_user(
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_db),
) -> Response:
    await HierarchyService(session).delete_user(
        user_id,
        tenant_id=get_selected_tenant_id(request),
    )
    return Response(status_code=204)
