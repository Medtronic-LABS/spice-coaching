"""SyncService.get_video_progress_bundle — assignment ∩ video ∩ delta filters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from platform_service.db.models.document_assignment import DocumentAssignment
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.repositories.video_progress_repository import VideoProgressRepository
from platform_service.services.sync_service import SyncService
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.helpers.hierarchy_fixtures import SK_ID, SK_OTHER_ID, seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]

_TENANT_ID = 1


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text(
            "TRUNCATE chw_video_progress, document_assignment, source_document, "
            "users, upazila, district RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()


async def _seed_doc(
    session: AsyncSession,
    *,
    title: str = "assigned-video",
    source_type: str = "video",
    tenant_id: int = _TENANT_ID,
) -> SourceDocument:
    doc = SourceDocument(
        title=title,
        source_type=source_type,
        primary_language="bn",
        content_domain="clinical",
        original_storage_path=f"medtronics-storage/ingest/{uuid4()}.bin",
        original_filename="clip.mp4" if source_type == "video" else "doc.pdf",
        status="ingested",
        tenant_id=tenant_id,
    )
    session.add(doc)
    await session.flush()
    return doc


async def _assign(
    session: AsyncSession,
    *,
    doc: SourceDocument,
    user_id: int = SK_ID,
    tenant_id: int = _TENANT_ID,
) -> None:
    session.add(
        DocumentAssignment(
            id=uuid4(),
            source_document_id=doc.id,
            user_id=user_id,
            assigned_by=user_id,
            tenant_id=tenant_id,
        )
    )
    await session.flush()


async def _progress(
    session: AsyncSession,
    *,
    doc: SourceDocument,
    chw_id: int = SK_ID,
    tenant_id: int = _TENANT_ID,
    last_position_ms: int = 5_000,
    percent_watched: float = 25.0,
    completed: bool = False,
) -> None:
    await VideoProgressRepository(session).upsert(
        chw_id=chw_id,
        source_document_id=doc.id,
        last_position_ms=last_position_ms,
        percent_watched=percent_watched,
        completed=completed,
        tenant_id=tenant_id,
    )


async def test_returns_assigned_video_progress_after_since(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    doc = await _seed_doc(db_session)
    await _assign(db_session, doc=doc)
    await _progress(db_session, doc=doc, last_position_ms=12_000, percent_watched=40.0)
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(hours=1)
    bundle = await SyncService(db_session).get_video_progress_bundle(
        since=since,
        user_id=SK_ID,
        tenant_id=_TENANT_ID,
    )

    assert len(bundle.videos) == 1
    item = bundle.videos[0]
    assert item.source_document_id == doc.id
    assert item.last_position_ms == 12_000
    assert item.percent_watched == 40.0
    assert item.completed is False
    assert item.last_watched_at is not None
    assert bundle.server_time_utc


async def test_excludes_progress_before_since(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    doc = await _seed_doc(db_session)
    await _assign(db_session, doc=doc)
    await _progress(db_session, doc=doc)
    await db_session.commit()

    old = datetime.now(UTC) - timedelta(days=2)
    await db_session.execute(
        text("UPDATE chw_video_progress SET updated_at = :ts WHERE source_document_id = :id"),
        {"ts": old, "id": doc.id},
    )
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(hours=1)
    bundle = await SyncService(db_session).get_video_progress_bundle(
        since=since,
        user_id=SK_ID,
        tenant_id=_TENANT_ID,
    )
    assert bundle.videos == []


async def test_excludes_revoked_assignment(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    doc = await _seed_doc(db_session)
    await _progress(db_session, doc=doc)
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(hours=1)
    bundle = await SyncService(db_session).get_video_progress_bundle(
        since=since,
        user_id=SK_ID,
        tenant_id=_TENANT_ID,
    )
    assert bundle.videos == []


async def test_excludes_non_video_source_type(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    doc = await _seed_doc(db_session, title="assigned-pdf", source_type="pdf")
    await _assign(db_session, doc=doc)
    await _progress(db_session, doc=doc)
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(hours=1)
    bundle = await SyncService(db_session).get_video_progress_bundle(
        since=since,
        user_id=SK_ID,
        tenant_id=_TENANT_ID,
    )
    assert bundle.videos == []


async def test_excludes_other_user_and_tenant(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    own = await _seed_doc(db_session, title="own-video")
    other_user = await _seed_doc(db_session, title="other-user-video")
    other_tenant = await _seed_doc(db_session, title="other-tenant-video", tenant_id=2)

    await _assign(db_session, doc=own, user_id=SK_ID)
    await _assign(db_session, doc=other_user, user_id=SK_OTHER_ID)
    await _assign(db_session, doc=other_tenant, user_id=SK_ID, tenant_id=2)

    await _progress(db_session, doc=own, chw_id=SK_ID, tenant_id=_TENANT_ID)
    await _progress(db_session, doc=other_user, chw_id=SK_OTHER_ID, tenant_id=_TENANT_ID)
    await _progress(db_session, doc=other_tenant, chw_id=SK_ID, tenant_id=2)
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(hours=1)
    bundle = await SyncService(db_session).get_video_progress_bundle(
        since=since,
        user_id=SK_ID,
        tenant_id=_TENANT_ID,
    )
    assert [v.source_document_id for v in bundle.videos] == [own.id]


async def test_orders_by_updated_at_asc(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    first = await _seed_doc(db_session, title="first")
    second = await _seed_doc(db_session, title="second")
    await _assign(db_session, doc=first)
    await _assign(db_session, doc=second)
    await _progress(db_session, doc=second, percent_watched=10.0)
    await _progress(db_session, doc=first, percent_watched=20.0)
    await db_session.commit()

    earlier = datetime.now(UTC) - timedelta(minutes=10)
    later = datetime.now(UTC) - timedelta(minutes=5)
    await db_session.execute(
        text("UPDATE chw_video_progress SET updated_at = :ts WHERE source_document_id = :id"),
        {"ts": earlier, "id": first.id},
    )
    await db_session.execute(
        text("UPDATE chw_video_progress SET updated_at = :ts WHERE source_document_id = :id"),
        {"ts": later, "id": second.id},
    )
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(hours=1)
    bundle = await SyncService(db_session).get_video_progress_bundle(
        since=since,
        user_id=SK_ID,
        tenant_id=_TENANT_ID,
    )
    assert [v.source_document_id for v in bundle.videos] == [first.id, second.id]


async def test_empty_when_unwatched_assigned_video(db_session: AsyncSession) -> None:
    await seed_basic_hierarchy(db_session)
    doc = await _seed_doc(db_session)
    await _assign(db_session, doc=doc)
    await db_session.commit()

    since = datetime.now(UTC) - timedelta(hours=1)
    bundle = await SyncService(db_session).get_video_progress_bundle(
        since=since,
        user_id=SK_ID,
        tenant_id=_TENANT_ID,
    )
    assert bundle.videos == []
