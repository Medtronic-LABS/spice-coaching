"""Repository for DocumentAssignment database operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.document_assignment import DocumentAssignment


class DocumentAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_user_assignment(
        self,
        source_document_id: UUID,
        user_id: int,
    ) -> DocumentAssignment | None:
        """Find an existing user assignment."""
        stmt = select(DocumentAssignment).where(
            DocumentAssignment.source_document_id == source_document_id,
            DocumentAssignment.user_id == user_id,
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def list_user_ids_for_document(
        self,
        source_document_id: UUID,
        *,
        tenant_id: int,
    ) -> list[int]:
        """Return assignee user ids for a source document within a tenant."""
        stmt = (
            select(DocumentAssignment.user_id)
            .where(
                DocumentAssignment.source_document_id == source_document_id,
                DocumentAssignment.tenant_id == tenant_id,
            )
            .order_by(DocumentAssignment.user_id)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_for_user(
        self,
        user_id: int,
        *,
        tenant_id: int,
    ) -> list[DocumentAssignment]:
        """Return all document assignments for a user within a tenant."""
        stmt = (
            select(DocumentAssignment)
            .where(
                DocumentAssignment.user_id == user_id,
                DocumentAssignment.tenant_id == tenant_id,
            )
            .order_by(DocumentAssignment.assigned_at.asc(), DocumentAssignment.id.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    def add_assignment(self, assignment: DocumentAssignment) -> None:
        """Add a new assignment to the session."""
        self._session.add(assignment)

    async def delete_assignments_for_users(
        self,
        source_document_id: UUID,
        user_ids: set[int],
        *,
        tenant_id: int,
    ) -> int:
        """Delete assignment rows for the given users on a document within a tenant."""
        if not user_ids:
            return 0
        stmt = delete(DocumentAssignment).where(
            DocumentAssignment.source_document_id == source_document_id,
            DocumentAssignment.tenant_id == tenant_id,
            DocumentAssignment.user_id.in_(user_ids),
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount)

    async def list_assignment_ids_for_document(
        self,
        source_document_id: UUID,
        *,
        tenant_id: int,
    ) -> list[UUID]:
        """Return assignment row ids for a source document within a tenant."""
        stmt = (
            select(DocumentAssignment.id)
            .where(
                DocumentAssignment.source_document_id == source_document_id,
                DocumentAssignment.tenant_id == tenant_id,
            )
            .order_by(DocumentAssignment.id)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def source_document_ids_with_assignments(
        self,
        source_document_ids: list[UUID],
    ) -> set[UUID]:
        """Return the subset of document ids that have at least one assignment."""
        if not source_document_ids:
            return set()
        stmt = (
            select(DocumentAssignment.source_document_id)
            .where(DocumentAssignment.source_document_id.in_(source_document_ids))
            .distinct()
        )
        return set((await self._session.execute(stmt)).scalars().all())
