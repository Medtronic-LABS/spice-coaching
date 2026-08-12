"""SyncService.get_source_documents_bundle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from mc_foundation.objectstore import PresignedObjectUrl
from platform_service.config import Settings
from platform_service.db.models.document_assignment import DocumentAssignment
from platform_service.services.sync_service import SyncService
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import _seed_module, _seed_source_document
from tests.conftest import requires_db
from tests.helpers.hierarchy_fixtures import SK_ID, SK_OTHER_ID, seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]

_PRESIGNED_URL = "https://minio.example/presigned"
_THUMB_URL = "https://minio.example/thumb"
_TENANT_ID = 1


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text(
            "TRUNCATE module_quiz_question, module, module_family, "
            "document_assignment, source_document, users, upazila, district "
            "RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()


def _mock_storage() -> MagicMock:
    storage = MagicMock()

    async def _presign(*, object_name: str, expires_seconds: int, download_filename=None):
        if "thumbnails" in object_name:
            return PresignedObjectUrl(
                url=_THUMB_URL,
                bucket_name="medtronics-storage",
                object_name=object_name,
                expires_seconds=expires_seconds,
            )
        return PresignedObjectUrl(
            url=_PRESIGNED_URL,
            bucket_name="medtronics-storage",
            object_name=object_name,
            expires_seconds=expires_seconds,
        )

    storage.presigned_get_url = AsyncMock(side_effect=_presign)
    storage.stat_object = AsyncMock()
    return storage


async def _bundle(
    session: AsyncSession,
    *,
    since: datetime,
    user_id: int | None = SK_ID,
    tenant_id: int = _TENANT_ID,
):
    return await SyncService(session).get_source_documents_bundle(
        since=since,
        storage=_mock_storage(),
        tenant_id=tenant_id,
        user_id=user_id,
    )


async def test_module_linked_doc_updated_after_since(db_session: AsyncSession) -> None:
    doc = await _seed_source_document(db_session, sync_published_visible=False)
    await _seed_module(db_session, source_document_ids=[doc.id])
    since = datetime.now(UTC) - timedelta(hours=1)

    bundle = await _bundle(db_session, since=since)

    assert len(bundle.source_documents) == 1
    entry = bundle.source_documents[0]
    assert entry.source_document_id == doc.id
    assert entry.title == doc.title
    assert entry.source_type == doc.source_type
    assert entry.original_filename == doc.original_filename
    assert entry.assigned_at is None
    assert entry.presigned_url == _PRESIGNED_URL
    assert entry.presigned_expires_seconds == Settings().admin_file_presigned_max_seconds
    assert bundle.assigned_documents == []


async def test_includes_thumbnail_presigned_url(db_session: AsyncSession) -> None:
    doc = await _seed_source_document(db_session, sync_published_visible=False)
    doc.thumbnail_storage_path = f"medtronics-storage/ingest/thumbnails/{doc.id}.png"
    await db_session.commit()
    await _seed_module(db_session, source_document_ids=[doc.id])
    since = datetime.now(UTC) - timedelta(hours=1)

    bundle = await _bundle(db_session, since=since)

    entry = bundle.source_documents[0]
    assert entry.thumbnail_presigned_url == _THUMB_URL
    assert entry.thumbnail_presigned_expires_seconds == Settings().admin_file_presigned_max_seconds


async def test_omits_module_linked_doc_when_updated_at_not_after_since(
    db_session: AsyncSession,
) -> None:
    doc = await _seed_source_document(db_session)
    await _seed_module(db_session, source_document_ids=[doc.id])
    since = datetime.now(UTC) + timedelta(hours=1)

    bundle = await _bundle(db_session, since=since)

    assert bundle.source_documents == []


async def test_omits_doc_on_unpublished_module(db_session: AsyncSession) -> None:
    doc = await _seed_source_document(db_session)
    await _seed_module(db_session, source_document_ids=[doc.id], lifecycle_status="draft")
    since = datetime.now(UTC) - timedelta(hours=1)

    bundle = await _bundle(db_session, since=since)

    assert bundle.source_documents == []


async def test_includes_sync_published_visible_false_when_module_linked(
    db_session: AsyncSession,
) -> None:
    doc = await _seed_source_document(db_session, sync_published_visible=False)
    await _seed_module(db_session, source_document_ids=[doc.id])
    since = datetime.now(UTC) - timedelta(hours=1)

    bundle = await _bundle(db_session, since=since)

    assert [d.source_document_id for d in bundle.source_documents] == [doc.id]


async def test_excludes_retired_from_module_linked(db_session: AsyncSession) -> None:
    active = await _seed_source_document(db_session, title="Active")
    retired = await _seed_source_document(db_session, title="Retired")
    retired.status = "retired"
    await db_session.commit()
    await _seed_module(db_session, source_document_ids=[active.id, retired.id])
    since = datetime.now(UTC) - timedelta(hours=1)

    bundle = await _bundle(db_session, since=since)

    assert [d.source_document_id for d in bundle.source_documents] == [active.id]


async def test_assigned_documents_full_snapshot_ignores_since(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    doc = await _seed_source_document(db_session, title="Assigned-only")
    # Force updated_at into the past so module-style since would skip it.
    await db_session.execute(
        text("UPDATE source_document SET updated_at = :ts WHERE id = :id"),
        {"ts": datetime.now(UTC) - timedelta(days=30), "id": doc.id},
    )
    await db_session.commit()
    db_session.add(
        DocumentAssignment(
            id=uuid4(),
            source_document_id=doc.id,
            user_id=SK_ID,
            assigned_by=SK_ID,
            tenant_id=_TENANT_ID,
        )
    )
    await db_session.commit()
    since = datetime.now(UTC) - timedelta(hours=1)

    bundle = await _bundle(db_session, since=since, user_id=SK_ID)

    assert bundle.source_documents == []
    assert len(bundle.assigned_documents) == 1
    entry = bundle.assigned_documents[0]
    assert entry.source_document_id == doc.id
    assert entry.assigned_at is not None
    assert entry.presigned_url == _PRESIGNED_URL


async def test_assigned_documents_excludes_other_users(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    doc = await _seed_source_document(db_session)
    db_session.add(
        DocumentAssignment(
            id=uuid4(),
            source_document_id=doc.id,
            user_id=SK_OTHER_ID,
            assigned_by=SK_ID,
            tenant_id=_TENANT_ID,
        )
    )
    await db_session.commit()
    since = datetime.now(UTC) - timedelta(hours=1)

    bundle = await _bundle(db_session, since=since, user_id=SK_ID)

    assert bundle.assigned_documents == []


async def test_assigned_documents_excludes_retired(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    doc = await _seed_source_document(db_session, title="Retired-assigned")
    doc.status = "retired"
    await db_session.commit()
    db_session.add(
        DocumentAssignment(
            id=uuid4(),
            source_document_id=doc.id,
            user_id=SK_ID,
            assigned_by=SK_ID,
            tenant_id=_TENANT_ID,
        )
    )
    await db_session.commit()
    since = datetime.now(UTC) - timedelta(hours=1)

    bundle = await _bundle(db_session, since=since, user_id=SK_ID)

    assert bundle.assigned_documents == []


async def test_overlap_allowed_in_both_lists(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    doc = await _seed_source_document(db_session)
    await _seed_module(db_session, source_document_ids=[doc.id])
    db_session.add(
        DocumentAssignment(
            id=uuid4(),
            source_document_id=doc.id,
            user_id=SK_ID,
            assigned_by=SK_ID,
            tenant_id=_TENANT_ID,
        )
    )
    await db_session.commit()
    since = datetime.now(UTC) - timedelta(hours=1)

    bundle = await _bundle(db_session, since=since, user_id=SK_ID)

    assert [d.source_document_id for d in bundle.source_documents] == [doc.id]
    assert [d.source_document_id for d in bundle.assigned_documents] == [doc.id]


async def test_tenant_scoping_excludes_other_tenant_modules(db_session: AsyncSession) -> None:
    doc = await _seed_source_document(db_session)
    await _seed_module(db_session, source_document_ids=[doc.id])
    since = datetime.now(UTC) - timedelta(hours=1)

    bundle = await _bundle(db_session, since=since, tenant_id=999, user_id=None)

    assert bundle.source_documents == []
    assert bundle.assigned_documents == []
