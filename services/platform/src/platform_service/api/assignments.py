from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from mc_contracts.assignments import (
    AssignmentCreateRequest,
    AssignmentUpdateRequest,
    AssignmentUpdateResponse,
    DocumentAssignmentCreateRequest,
    DocumentAssignmentUpdateRequest,
    DocumentAssignmentUsersResponse,
    ModuleAssignmentUsersResponse,
)
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_user import get_selected_tenant_id
from platform_service.deps import get_db
from platform_service.services.document_assignment_service import (
    DocumentAssignmentService,
    SourceDocumentNotFoundError,
)
from platform_service.services.module_assignment_service import (
    AssignmentValidationError,
    ModuleAssignmentService,
    ModuleNotFoundError,
)

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


@router.post("/assignments", status_code=201)
async def create_assignments(
    request: Request,
    body: AssignmentCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create module assignments for hierarchy users.

    PO ``user_ids`` assign only the PO unless ``expand_po_assignees`` is true
    (then the PO plus their direct SK children). ``upazila_ids`` expand to
    PO/SK users in that upazila. ``district_ids`` and ``division_ids`` expand
    to all hierarchy users in that geography, including Area Managers.
    """
    spice_user = getattr(request.state, "spice_user", None)
    assigned_by = spice_user.id if spice_user and spice_user.id is not None else 1
    tenant_id = get_selected_tenant_id(request)

    service = ModuleAssignmentService(session)
    try:
        return await service.create_assignments(body, assigned_by, tenant_id=tenant_id)
    except ModuleNotFoundError as exc:
        raise AppError(ErrorCode.MODULE_NOT_FOUND.value, str(exc), status=404) from exc
    except AssignmentValidationError as exc:
        raise AppError(ErrorCode.ASSIGNMENT_VALIDATION_ERROR.value, str(exc), status=400) from exc


@router.get("/assignments/{module_id}/users", response_model=ModuleAssignmentUsersResponse)
async def list_module_assigned_users(
    request: Request,
    module_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> ModuleAssignmentUsersResponse:
    """List PO/SK users assigned to a module."""
    tenant_id = get_selected_tenant_id(request)
    service = ModuleAssignmentService(session)
    try:
        return await service.list_assigned_users(module_id, tenant_id=tenant_id)
    except ModuleNotFoundError as exc:
        raise AppError(ErrorCode.MODULE_NOT_FOUND.value, str(exc), status=404) from exc


@router.put("/assignments/{module_id}/users", response_model=AssignmentUpdateResponse)
async def update_module_assigned_users(
    request: Request,
    module_id: UUID,
    body: AssignmentUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> AssignmentUpdateResponse:
    """Replace hierarchy users assigned to a module.

    Uses the same PO expand, ``upazila_ids``, ``district_ids``, and
    ``division_ids`` rules as create (including optional ``expand_po_assignees``).
    """
    spice_user = getattr(request.state, "spice_user", None)
    assigned_by = spice_user.id if spice_user and spice_user.id is not None else 1
    tenant_id = get_selected_tenant_id(request)

    service = ModuleAssignmentService(session)
    try:
        return await service.update_assignments(
            module_id,
            body,
            assigned_by,
            tenant_id=tenant_id,
        )
    except ModuleNotFoundError as exc:
        raise AppError(ErrorCode.MODULE_NOT_FOUND.value, str(exc), status=404) from exc
    except AssignmentValidationError as exc:
        raise AppError(ErrorCode.ASSIGNMENT_VALIDATION_ERROR.value, str(exc), status=400) from exc


@router.post("/document-assignments", status_code=201)
async def create_document_assignments(
    request: Request,
    body: DocumentAssignmentCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create document assignments for hierarchy users.

    PO ``user_ids`` assign only the PO unless ``expand_po_assignees`` is true
    (then the PO plus their direct SK children). ``upazila_ids`` expand to
    PO/SK users in that upazila. ``district_ids`` and ``division_ids`` expand
    to all hierarchy users in that geography, including Area Managers.
    """
    spice_user = getattr(request.state, "spice_user", None)
    assigned_by = spice_user.id if spice_user and spice_user.id is not None else 1
    tenant_id = get_selected_tenant_id(request)

    service = DocumentAssignmentService(session)
    try:
        return await service.create_assignments(body, assigned_by, tenant_id=tenant_id)
    except SourceDocumentNotFoundError as exc:
        raise AppError(ErrorCode.SOURCE_DOCUMENT_NOT_FOUND.value, str(exc), status=404) from exc
    except AssignmentValidationError as exc:
        raise AppError(ErrorCode.ASSIGNMENT_VALIDATION_ERROR.value, str(exc), status=400) from exc


@router.get(
    "/document-assignments/{source_document_id}/users",
    response_model=DocumentAssignmentUsersResponse,
)
async def list_document_assigned_users(
    request: Request,
    source_document_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> DocumentAssignmentUsersResponse:
    """List PO/SK users assigned to a source document."""
    tenant_id = get_selected_tenant_id(request)
    service = DocumentAssignmentService(session)
    try:
        return await service.list_assigned_users(source_document_id, tenant_id=tenant_id)
    except SourceDocumentNotFoundError as exc:
        raise AppError(ErrorCode.SOURCE_DOCUMENT_NOT_FOUND.value, str(exc), status=404) from exc


@router.put(
    "/document-assignments/{source_document_id}/users",
    response_model=AssignmentUpdateResponse,
)
async def update_document_assigned_users(
    request: Request,
    source_document_id: UUID,
    body: DocumentAssignmentUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> AssignmentUpdateResponse:
    """Replace hierarchy users assigned to a source document.

    Uses the same PO expand, ``upazila_ids``, ``district_ids``, and
    ``division_ids`` rules as create (including optional ``expand_po_assignees``).
    """
    spice_user = getattr(request.state, "spice_user", None)
    assigned_by = spice_user.id if spice_user and spice_user.id is not None else 1
    tenant_id = get_selected_tenant_id(request)

    service = DocumentAssignmentService(session)
    try:
        return await service.update_assignments(
            source_document_id,
            body,
            assigned_by,
            tenant_id=tenant_id,
        )
    except SourceDocumentNotFoundError as exc:
        raise AppError(ErrorCode.SOURCE_DOCUMENT_NOT_FOUND.value, str(exc), status=404) from exc
    except AssignmentValidationError as exc:
        raise AppError(ErrorCode.ASSIGNMENT_VALIDATION_ERROR.value, str(exc), status=400) from exc
