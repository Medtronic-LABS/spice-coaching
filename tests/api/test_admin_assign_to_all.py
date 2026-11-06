"""Admin ``assign_to_all`` — publish option, PUT toggles, and response fields."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from platform_service.db.models.module import Module
from platform_service.db.models.source_document import SourceDocument
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import _seed_module, _seed_source_document
from tests.conftest import platform_path, requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


async def _seed_video_document(session: AsyncSession, *, assign_to_all: bool = False) -> SourceDocument:
    doc = SourceDocument(
        title="clip",
        source_type="video",
        primary_language="bn",
        content_domain="clinical",
        original_storage_path=f"medtronics-storage/ingest/{uuid4()}.mp4",
        original_filename="clip.mp4",
        status="ingested",
        assign_to_all=assign_to_all,
        tenant_id=1,
    )
    session.add(doc)
    await session.flush()
    await session.commit()
    return doc


@pytest.fixture
def _skip_publish_enrichment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Publish enrichment needs seeded prompt templates and the AI runtime; not under test here."""
    monkeypatch.setattr(
        "platform_service.services.module_publish_service.enrich_module_for_publish",
        AsyncMock(return_value=None),
    )


@pytest.mark.usefixtures("_skip_publish_enrichment")
class TestPublishAssignToAll:
    async def test_publish_sets_module_and_linked_video_docs_only(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        video = await _seed_video_document(db_session)
        pdf = await _seed_source_document(db_session)
        mod = await _seed_module(
            db_session,
            lifecycle_status="draft",
            published_at=None,
            source_document_ids=[video.id, pdf.id],
        )

        resp = await client.post(
            platform_path(f"/admin/modules/{mod.id}/publish"),
            json={"assign_to_all": True},
        )

        assert resp.status_code == 200
        await db_session.refresh(mod)
        await db_session.refresh(video)
        await db_session.refresh(pdf)
        assert mod.assign_to_all is True
        assert video.assign_to_all is True
        assert pdf.assign_to_all is False

    async def test_publish_false_clears_flags(self, client: AsyncClient, db_session: AsyncSession) -> None:
        video = await _seed_video_document(db_session, assign_to_all=True)
        mod = await _seed_module(
            db_session,
            lifecycle_status="draft",
            published_at=None,
            source_document_ids=[video.id],
            assign_to_all=True,
        )

        resp = await client.post(
            platform_path(f"/admin/modules/{mod.id}/publish"),
            json={"assign_to_all": False},
        )

        assert resp.status_code == 200
        await db_session.refresh(mod)
        await db_session.refresh(video)
        assert mod.assign_to_all is False
        assert video.assign_to_all is False

    async def test_publish_without_field_leaves_flags_unchanged(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        video = await _seed_video_document(db_session, assign_to_all=True)
        mod = await _seed_module(
            db_session,
            lifecycle_status="draft",
            published_at=None,
            source_document_ids=[video.id],
            assign_to_all=False,
        )

        resp = await client.post(platform_path(f"/admin/modules/{mod.id}/publish"), json={})

        assert resp.status_code == 200
        await db_session.refresh(mod)
        await db_session.refresh(video)
        assert mod.assign_to_all is False
        assert video.assign_to_all is True


class TestModuleAssignToAllEndpoint:
    async def test_put_sets_flag_and_cascades_to_videos(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        video = await _seed_video_document(db_session)
        mod = await _seed_module(db_session, source_document_ids=[video.id])

        resp = await client.put(
            platform_path(f"/admin/modules/{mod.id}/assign-to-all"),
            json={"assign_to_all": True},
        )

        assert resp.status_code == 200
        assert resp.json() == {"module_id": str(mod.id), "assign_to_all": True}
        await db_session.refresh(video)
        assert video.assign_to_all is True

        resp = await client.put(
            platform_path(f"/admin/modules/{mod.id}/assign-to-all"),
            json={"assign_to_all": False},
        )
        assert resp.json() == {"module_id": str(mod.id), "assign_to_all": False}
        loaded = await db_session.get(Module, mod.id, populate_existing=True)
        assert loaded is not None
        assert loaded.assign_to_all is False

    async def test_put_unknown_module_returns_404(self, client: AsyncClient) -> None:
        resp = await client.put(
            platform_path(f"/admin/modules/{uuid4()}/assign-to-all"),
            json={"assign_to_all": True},
        )
        assert resp.status_code == 404

    async def test_put_requires_boolean_body(self, client: AsyncClient, db_session: AsyncSession) -> None:
        mod = await _seed_module(db_session)
        resp = await client.put(platform_path(f"/admin/modules/{mod.id}/assign-to-all"), json={})
        assert resp.status_code == 422

    async def test_module_detail_and_list_include_flag(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        mod = await _seed_module(db_session, assign_to_all=True)

        detail = await client.get(platform_path(f"/admin/modules/{mod.id}"))
        assert detail.status_code == 200
        assert detail.json()["assign_to_all"] is True

        listing = await client.get(platform_path("/admin/modules"), headers={"x-mock-user-id": "1"})
        assert listing.status_code == 200
        row = next(m for m in listing.json()["modules"] if m["id"] == str(mod.id))
        assert row["assign_to_all"] is True


class TestSourceDocumentAssignToAllEndpoint:
    async def test_put_sets_flag(self, client: AsyncClient, db_session: AsyncSession) -> None:
        doc = await _seed_source_document(db_session)

        resp = await client.put(
            platform_path(f"/admin/source-documents/{doc.id}/assign-to-all"),
            json={"assign_to_all": True},
        )

        assert resp.status_code == 200
        assert resp.json() == {"source_document_id": str(doc.id), "assign_to_all": True}
        await db_session.refresh(doc)
        assert doc.assign_to_all is True

    async def test_put_unknown_document_returns_404(self, client: AsyncClient) -> None:
        resp = await client.put(
            platform_path(f"/admin/source-documents/{uuid4()}/assign-to-all"),
            json={"assign_to_all": True},
        )
        assert resp.status_code == 404

    async def test_list_includes_flag(self, client: AsyncClient, db_session: AsyncSession) -> None:
        doc = await _seed_source_document(db_session, assign_to_all=True)

        resp = await client.get(platform_path("/admin/source-documents"))

        assert resp.status_code == 200
        row = next(d for d in resp.json()["source_documents"] if d["id"] == str(doc.id))
        assert row["assign_to_all"] is True
