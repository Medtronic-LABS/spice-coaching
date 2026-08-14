"""Division / district / hierarchy-user API contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from mc_contracts.enums import HierarchyRole


class DivisionCreateRequest(BaseModel):
    name: str = Field(min_length=1)


class DivisionUpdateRequest(BaseModel):
    name: str = Field(min_length=1)


class DivisionResponse(BaseModel):
    id: int
    name: str
    tenant_id: int
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


class DivisionListResponse(BaseModel):
    divisions: list[DivisionResponse]
    total: int
    total_pages: int
    limit: int
    offset: int


class DistrictCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    division_id: int | None = None


class DistrictUpdateRequest(BaseModel):
    name: str = Field(min_length=1)
    division_id: int | None = None


class DistrictResponse(BaseModel):
    id: int
    name: str
    division_id: int | None
    division: str | None = None
    tenant_id: int
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


class DistrictListResponse(BaseModel):
    districts: list[DistrictResponse]
    total: int
    total_pages: int
    limit: int
    offset: int


class UpazilaCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    district_id: int


class UpazilaUpdateRequest(BaseModel):
    name: str = Field(min_length=1)
    district_id: int


class UpazilaResponse(BaseModel):
    id: int
    name: str
    district_id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


class UpazilaListResponse(BaseModel):
    upazilas: list[UpazilaResponse]
    total: int
    total_pages: int
    limit: int
    offset: int


class HierarchyUserCreateRequest(BaseModel):
    id: int = Field(gt=0, description="Externally supplied hierarchy user id (no DB sequence).")
    name: str = Field(min_length=1)
    role: HierarchyRole
    parent_id: int | None = None
    district_id: int
    upazila_ids: list[int] = Field(default_factory=list)


class HierarchyUserUpdateRequest(BaseModel):
    name: str = Field(min_length=1)
    role: HierarchyRole
    parent_id: int | None = None
    district_id: int
    upazila_ids: list[int] = Field(default_factory=list)


class HierarchyUserResponse(BaseModel):
    id: int
    name: str
    role: HierarchyRole
    parent_id: int | None
    district_id: int
    division_id: int | None = None
    division: str | None = None
    upazilas: list[UpazilaResponse] = Field(default_factory=list)
    tenant_id: int
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


class HierarchyUserListResponse(BaseModel):
    users: list[HierarchyUserResponse]
    total: int
    total_pages: int
    limit: int
    offset: int
