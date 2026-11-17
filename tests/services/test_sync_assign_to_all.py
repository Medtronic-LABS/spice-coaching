"""assign_to_all delivery rule across the modules / source-documents / video-progress syncs.

Rule: ``if assign_to_all: every SK elif explicit assignment row: that SK else: not assigned``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from mc_foundation.objectstore import PresignedObjectUrl
from platform_service.db.models.document_assignment import DocumentAssignment
from platform_service.db.models.module_assignment import ModuleAssignment
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.repositories.video_progress_repository import VideoProgressRepository
from platform_service.services.sync_service import SyncService
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import _seed_module
from tests.conftest import requires_db
from tests.helpers.hierarchy_fixtures import SK_ID, SK_OTHER_ID, seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]

_TENANT_ID = 1
_SINCE = datetime(2020, 1, 1, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text(
            "TRUNCATE chw_video_progress, module_quiz_question, module_assignment, module, "
            "module_family, document_assignment, source_document, users, upazila, district "
            "RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()


def _mock_storage() -> MagicMock:
    storage = MagicMock()

    async def _presign(*, object_name: str, expires_seconds: int, **_kwargs: object):
        return PresignedObjectUrl(
            url="https://minio.example/presigned",
            bucket_name="medtronics-storage",
            object_name=object_name,
            expires_seconds=expires_seconds,
        )

    storage.presigned_get_url = AsyncMock(side_effect=_presign)
    storage.stat_object = AsyncMock()
    return storage


async def _seed_doc(
    session: AsyncSession,
    *,
    source_type: str = "video",
    assign_to_all: bool,
    status: str = "ingested",
    tenant_id: int = _TENANT_ID,
) -> SourceDocument:
    doc = SourceDocument(
        title=f"{source_type}-doc",
        source_type=source_type,
        primary_language="bn",
        content_domain="clinical",
        original_storage_path=f"medtronics-storage/ingest/{uuid4()}.bin",
        original_filename="clip.mp4",
        status=status,
        assign_to_all=assign_to_all,
        tenant_id=tenant_id,
    )
    session.add(doc)
    await session.flush()
    return doc


async def _docs_bundle(session: AsyncSession, *, user_id: int | None):
    return await SyncService(session).get_source_documents_bundle(
        since=_SINCE,
        storage=_mock_storage(),
        tenant_id=_TENANT_ID,
        user_id=user_id,
    )


async def _module_ids(session: AsyncSession, *, user_id: int | None) -> set:
    bundle = await SyncService(session).get_modules_bundle(
        since=_SINCE,
        tenant_id=_TENANT_ID,
        user_id=user_id,
    )
    return {entry.module_id for entry in bundle.assigned_module_ids}


class TestModulesAssignToAll:
    async def test_flagged_module_assigned_without_row(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        flagged = await _seed_module(db_session, assign_to_all=True)

        assert await _module_ids(db_session, user_id=SK_ID) == {flagged.id}

    async def test_unflagged_without_row_not_assigned(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        await _seed_module(db_session, assign_to_all=False)

        assert await _module_ids(db_session, user_id=SK_ID) == set()

    async def test_unflagged_with_explicit_row_assigned_only_to_that_user(
        self, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        module = await _seed_module(db_session, assign_to_all=False)
        db_session.add(
            ModuleAssignment(
                id=uuid4(),
                module_id=module.id,
                user_id=SK_ID,
                assigned_by=SK_ID,
                tenant_id=_TENANT_ID,
            )
        )
        await db_session.commit()

        assert await _module_ids(db_session, user_id=SK_ID) == {module.id}
        assert await _module_ids(db_session, user_id=SK_OTHER_ID) == set()

    async def test_flagged_and_explicit_row_deduplicated(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        module = await _seed_module(db_session, assign_to_all=True)
        db_session.add(
            ModuleAssignment(
                id=uuid4(),
                module_id=module.id,
                user_id=SK_ID,
                assigned_by=SK_ID,
                tenant_id=_TENANT_ID,
            )
        )
        await db_session.commit()

        bundle = await SyncService(db_session).get_modules_bundle(
            since=_SINCE, tenant_id=_TENANT_ID, user_id=SK_ID
        )
        assert [e.module_id for e in bundle.assigned_module_ids] == [module.id]

    async def test_flagged_module_assigned_when_user_id_none(self, db_session: AsyncSession) -> None:
        flagged = await _seed_module(db_session, assign_to_all=True)
        await _seed_module(db_session, assign_to_all=False)

        assert await _module_ids(db_session, user_id=None) == {flagged.id}

    async def test_flagged_draft_and_faq_modules_not_assigned(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        await _seed_module(db_session, assign_to_all=True, lifecycle_status="draft", published_at=None)
        await _seed_module(db_session, assign_to_all=True, chatbot_faqs_only=True)

        assert await _module_ids(db_session, user_id=SK_ID) == set()


class TestSourceDocumentsAssignToAll:
    async def test_flagged_video_in_assigned_documents_without_row(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        doc = await _seed_doc(db_session, assign_to_all=True)
        await db_session.commit()

        bundle = await _docs_bundle(db_session, user_id=SK_ID)

        assert [d.source_document_id for d in bundle.assigned_documents] == [doc.id]
        assert bundle.assigned_documents[0].assigned_at is not None
        assert bundle.assigned_documents[0].source_type == "video"

    async def test_unflagged_without_row_excluded(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        await _seed_doc(db_session, assign_to_all=False)
        await db_session.commit()

        bundle = await _docs_bundle(db_session, user_id=SK_ID)

        assert bundle.assigned_documents == []

    async def test_unflagged_with_explicit_row_included_for_that_user_only(
        self, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        doc = await _seed_doc(db_session, assign_to_all=False)
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

        mine = await _docs_bundle(db_session, user_id=SK_ID)
        other = await _docs_bundle(db_session, user_id=SK_OTHER_ID)

        assert [d.source_document_id for d in mine.assigned_documents] == [doc.id]
        assert other.assigned_documents == []

    async def test_flagged_plus_explicit_row_deduplicated(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        doc = await _seed_doc(db_session, assign_to_all=True)
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

        bundle = await _docs_bundle(db_session, user_id=SK_ID)

        assert [d.source_document_id for d in bundle.assigned_documents] == [doc.id]

    async def test_flagged_included_when_user_id_none(self, db_session: AsyncSession) -> None:
        flagged = await _seed_doc(db_session, assign_to_all=True)
        await _seed_doc(db_session, assign_to_all=False)
        await db_session.commit()

        bundle = await _docs_bundle(db_session, user_id=None)

        assert [d.source_document_id for d in bundle.assigned_documents] == [flagged.id]

    async def test_retired_and_other_tenant_flagged_docs_excluded(self, db_session: AsyncSession) -> None:
        await _seed_doc(db_session, assign_to_all=True, status="retired")
        await _seed_doc(db_session, assign_to_all=True, tenant_id=2)
        await db_session.commit()

        bundle = await _docs_bundle(db_session, user_id=None)

        assert bundle.assigned_documents == []

    async def test_flagged_non_video_type_included(self, db_session: AsyncSession) -> None:
        doc = await _seed_doc(db_session, source_type="pdf", assign_to_all=True)
        await db_session.commit()

        bundle = await _docs_bundle(db_session, user_id=None)

        assert [d.source_document_id for d in bundle.assigned_documents] == [doc.id]


class TestVideoProgressAssignToAll:
    async def _progress(self, session: AsyncSession, *, doc: SourceDocument, chw_id: int) -> None:
        await VideoProgressRepository(session).upsert(
            chw_id=chw_id,
            source_document_id=doc.id,
            last_position_ms=1_000,
            percent_watched=40.0,
            completed=False,
            tenant_id=_TENANT_ID,
        )
        await session.commit()

    async def _videos(self, session: AsyncSession, *, user_id: int) -> list:
        bundle = await SyncService(session).get_video_progress_bundle(
            since=datetime.now(UTC) - timedelta(hours=1),
            user_id=user_id,
            tenant_id=_TENANT_ID,
        )
        return [v.source_document_id for v in bundle.videos]

    async def test_flagged_video_progress_returned_without_row(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        doc = await _seed_doc(db_session, assign_to_all=True)
        await self._progress(db_session, doc=doc, chw_id=SK_ID)

        assert await self._videos(db_session, user_id=SK_ID) == [doc.id]

    async def test_unflagged_video_without_row_omitted(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        doc = await _seed_doc(db_session, assign_to_all=False)
        await self._progress(db_session, doc=doc, chw_id=SK_ID)

        assert await self._videos(db_session, user_id=SK_ID) == []

    async def test_flagged_and_explicit_row_returned_once(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        doc = await _seed_doc(db_session, assign_to_all=True)
        db_session.add(
            DocumentAssignment(
                id=uuid4(),
                source_document_id=doc.id,
                user_id=SK_ID,
                assigned_by=SK_ID,
                tenant_id=_TENANT_ID,
            )
        )
        await self._progress(db_session, doc=doc, chw_id=SK_ID)

        assert await self._videos(db_session, user_id=SK_ID) == [doc.id]
