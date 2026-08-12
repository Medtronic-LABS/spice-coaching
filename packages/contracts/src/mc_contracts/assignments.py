"""Assignments API contracts."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from mc_contracts.enums import HierarchyRole


class AssignmentUpazilaRef(BaseModel):
    id: int
    name: str


class UserResponse(BaseModel):
    id: int
    name: str
    role: HierarchyRole
    parent_id: int | None = None
    district_id: int
    district: str
    upazilas: list[AssignmentUpazilaRef] = Field(default_factory=list)


class AssignmentCreateRequest(BaseModel):
    module_id: UUID
    user_ids: list[int] | None = None
    upazilas: list[str] | None = None
    expand_po_assignees: bool = False


class DocumentAssignmentCreateRequest(BaseModel):
    source_document_id: UUID
    user_ids: list[int] | None = None
    upazilas: list[str] | None = None
    expand_po_assignees: bool = False


class ModuleAssignmentUsersResponse(BaseModel):
    module_id: UUID
    users: list[UserResponse]


class DocumentAssignmentUsersResponse(BaseModel):
    source_document_id: UUID
    users: list[UserResponse]


class AssignmentUpdateRequest(BaseModel):
    user_ids: list[int] | None = None
    upazilas: list[str] | None = None
    expand_po_assignees: bool = False


class DocumentAssignmentUpdateRequest(BaseModel):
    user_ids: list[int] | None = None
    upazilas: list[str] | None = None
    expand_po_assignees: bool = False


class AssignmentUpdateResponse(BaseModel):
    added_count: int
    removed_count: int
    assignment_ids: list[str]
