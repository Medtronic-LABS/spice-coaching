"""Badge catalog API contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from mc_contracts.actors import UserActorRef
from mc_contracts.localized import LocalizedString


class BadgeCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    image_storage_path: str = Field(min_length=1)
    module_ids: list[UUID] = Field(default_factory=list)
    sequence: int | None = Field(default=None, ge=1)


class BadgeUpdateRequest(BaseModel):
    name: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    image_storage_path: str = Field(min_length=1)
    module_ids: list[UUID] = Field(default_factory=list)
    sequence: int | None = Field(default=None, ge=1)


class BadgeModuleRef(BaseModel):
    """Linked module on a badge response (id + localized title for admin UI)."""

    id: UUID
    title: LocalizedString


class BadgeResponse(BaseModel):
    id: UUID
    name: str
    domain: str
    image_storage_path: str
    module_ids: list[UUID]
    modules: list[BadgeModuleRef] = Field(default_factory=list)
    status: str
    sequence: int | None = None
    created_at: datetime
    updated_at: datetime
    created_by: UserActorRef | None = None
    updated_by: UserActorRef | None = None


class BadgeListResponse(BaseModel):
    badges: list[BadgeResponse]
    total: int
    total_pages: int
    limit: int
    offset: int
