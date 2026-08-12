"""Service for document (source_document) assignment business logic."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from mc_contracts.assignments import (
    AssignmentUpdateResponse,
    DocumentAssignmentCreateRequest,
    DocumentAssignmentUpdateRequest,
    DocumentAssignmentUsersResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.document_assignment import DocumentAssignment
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.repositories.document_assignment_repository import DocumentAssignmentRepository
from platform_service.services.assignment_assignees import resolve_assignee_user_ids
from platform_service.services.hierarchy_user_mapping import hierarchy_users_by_id


class SourceDocumentNotFoundError(Exception):
    """Raised when the target source document is not found."""

    pass


class DocumentAssignmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DocumentAssignmentRepository(session)

    async def create_assignments(
        self,
        body: DocumentAssignmentCreateRequest,
        assigned_by: int,
        *,
        tenant_id: int = DEFAULT_TENANT_ID,
        commit: bool = True,
    ) -> dict[str, Any]:
        """Create document assignments for resolved PO/SK assignees."""
        document = await self._session.get(SourceDocument, body.source_document_id)
        if not document:
            raise SourceDocumentNotFoundError(f"Source document with ID {body.source_document_id} not found")

        users_by_id = await hierarchy_users_by_id(self._session, tenant_id=tenant_id)
        assignee_ids = resolve_assignee_user_ids(
            user_ids=body.user_ids,
            upazilas=body.upazilas,
            users_by_id=users_by_id,
            expand_po_assignees=body.expand_po_assignees,
        )

        created_ids = []
        for user_id in sorted(assignee_ids):
            existing = await self._repo.find_user_assignment(body.source_document_id, user_id)
            if existing:
                created_ids.append(existing.id)
                continue

            new_assignment = DocumentAssignment(
                source_document_id=body.source_document_id,
                user_id=user_id,
                tenant_id=tenant_id,
                assigned_by=assigned_by,
            )
            self._repo.add_assignment(new_assignment)
            await self._session.flush()
            created_ids.append(new_assignment.id)

        if commit:
            await self._session.commit()
        else:
            await self._session.flush()
        return {
            "assigned_count": len(created_ids),
            "assignment_ids": [str(x) for x in created_ids],
        }

    async def update_assignments(
        self,
        source_document_id: UUID,
        body: DocumentAssignmentUpdateRequest,
        assigned_by: int,
        *,
        tenant_id: int = DEFAULT_TENANT_ID,
        commit: bool = True,
    ) -> AssignmentUpdateResponse:
        """Replace document assignments with the resolved PO/SK assignee set."""
        document = await self._session.get(SourceDocument, source_document_id)
        if not document:
            raise SourceDocumentNotFoundError(f"Source document with ID {source_document_id} not found")
        if document.tenant_id is not None and document.tenant_id != tenant_id:
            raise SourceDocumentNotFoundError(f"Source document with ID {source_document_id} not found")

        users_by_id = await hierarchy_users_by_id(self._session, tenant_id=tenant_id)
        target_ids = resolve_assignee_user_ids(
            user_ids=body.user_ids,
            upazilas=body.upazilas,
            users_by_id=users_by_id,
            allow_empty=True,
            expand_po_assignees=body.expand_po_assignees,
        )

        current_ids = set(
            await self._repo.list_user_ids_for_document(
                source_document_id,
                tenant_id=tenant_id,
            )
        )
        to_add = target_ids - current_ids
        to_remove = current_ids - target_ids

        removed_count = await self._repo.delete_assignments_for_users(
            source_document_id,
            to_remove,
            tenant_id=tenant_id,
        )

        for user_id in sorted(to_add):
            new_assignment = DocumentAssignment(
                source_document_id=source_document_id,
                user_id=user_id,
                tenant_id=tenant_id,
                assigned_by=assigned_by,
            )
            self._repo.add_assignment(new_assignment)

        if commit:
            await self._session.commit()
        else:
            await self._session.flush()

        assignment_ids = await self._repo.list_assignment_ids_for_document(
            source_document_id,
            tenant_id=tenant_id,
        )
        return AssignmentUpdateResponse(
            added_count=len(to_add),
            removed_count=removed_count,
            assignment_ids=[str(assignment_id) for assignment_id in assignment_ids],
        )

    async def list_assigned_users(
        self,
        source_document_id: UUID,
        *,
        tenant_id: int = DEFAULT_TENANT_ID,
    ) -> DocumentAssignmentUsersResponse:
        """Return hierarchy user details for all assignees of a source document."""
        document = await self._session.get(SourceDocument, source_document_id)
        if not document:
            raise SourceDocumentNotFoundError(f"Source document with ID {source_document_id} not found")
        if document.tenant_id is not None and document.tenant_id != tenant_id:
            raise SourceDocumentNotFoundError(f"Source document with ID {source_document_id} not found")

        assignee_ids = await self._repo.list_user_ids_for_document(
            source_document_id,
            tenant_id=tenant_id,
        )
        users_by_id = await hierarchy_users_by_id(self._session, tenant_id=tenant_id)
        users = sorted(
            (users_by_id[user_id] for user_id in assignee_ids if user_id in users_by_id),
            key=lambda user: user.name.casefold(),
        )
        return DocumentAssignmentUsersResponse(source_document_id=source_document_id, users=users)
