"""Admin source document catalog API tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from platform_service.db.models.document_assignment import DocumentAssignment
from platform_service.db.models.ingestion_run import IngestionRun
from platform_service.deps import get_object_storage_client
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import _seed_source_document
from tests.conftest import platform_path, requires_db
from tests.helpers.hierarchy_fixtures import AM_ID, PO_ID, SK_ID, seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]


class TestListSourceDocuments:
    async def test_defaults_to_all_statuses(self, client: AsyncClient, db_session: AsyncSession) -> None:
        uploaded = await _seed_source_document(db_session, title="staged-doc")
        uploaded.status = "uploaded"
        ingesting = await _seed_source_document(db_session, title="in-flight-doc")
        ingesting.status = "ingesting"
        ingested = await _seed_source_document(db_session, title="ready-doc")
        ingested.status = "ingested"
        failed = await _seed_source_document(db_session, title="failed-doc")
        failed.status = "failed"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents"))
        assert resp.status_code == 200
        body = resp.json()
        rows = body["source_documents"]
        assert {row["title"] for row in rows} == {
            "staged-doc",
            "in-flight-doc",
            "ready-doc",
            "failed-doc",
        }
        assert {row["status"] for row in rows} == {"uploaded", "ingesting", "ingested", "failed"}
        assert body["total_source_documents"] == 4
        assert body["total_pages"] == 1
        assert body["limit"] == 50
        assert body["offset"] == 0

    async def test_orders_by_ingested_at_desc(self, client: AsyncClient, db_session: AsyncSession) -> None:
        older = await _seed_source_document(db_session, title="older")
        older.status = "ingested"
        older.ingested_at = datetime.now(UTC) - timedelta(days=2)
        newer = await _seed_source_document(db_session, title="newer")
        newer.status = "ingested"
        newer.ingested_at = datetime.now(UTC)
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents"))
        titles = [row["title"] for row in resp.json()["source_documents"]]
        assert titles == ["newer", "older"]

    async def test_status_filter_ingesting(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_source_document(db_session, title="in-flight")
        ingested = await _seed_source_document(db_session, title="done")
        ingested.status = "ingested"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?status=ingesting"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"in-flight"}
        assert body["total_source_documents"] == 1

    async def test_status_filter_uploaded(self, client: AsyncClient, db_session: AsyncSession) -> None:
        staged = await _seed_source_document(db_session, title="staged-only")
        staged.status = "uploaded"
        ingested = await _seed_source_document(db_session, title="done")
        ingested.status = "ingested"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?status=uploaded"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"staged-only"}
        assert body["total_source_documents"] == 1

    async def test_invalid_status_rejected(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/source-documents?status=unknown"))
        assert resp.status_code == 422

    async def test_invalid_status_in_multi_list_rejected(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/source-documents?status=uploaded&status=unknown"))
        assert resp.status_code == 422

    async def test_status_filter_multi_repeated(self, client: AsyncClient, db_session: AsyncSession) -> None:
        uploaded = await _seed_source_document(db_session, title="staged")
        uploaded.status = "uploaded"
        ingested = await _seed_source_document(db_session, title="done")
        ingested.status = "ingested"
        failed = await _seed_source_document(db_session, title="broke")
        failed.status = "failed"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?status=uploaded&status=ingested"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"staged", "done"}
        assert body["total_source_documents"] == 2

    async def test_status_filter_multi_comma_separated(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        uploaded = await _seed_source_document(db_session, title="staged")
        uploaded.status = "uploaded"
        ingested = await _seed_source_document(db_session, title="done")
        ingested.status = "ingested"
        failed = await _seed_source_document(db_session, title="broke")
        failed.status = "failed"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?status=uploaded,failed"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"staged", "broke"}
        assert body["total_source_documents"] == 2

    async def test_source_type_video_filter(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pdf = await _seed_source_document(db_session, title="pdf-doc", original_filename="guide.pdf")
        pdf.status = "ingested"
        video = await _seed_source_document(db_session, title="video-doc", original_filename="clip.mp4")
        video.status = "ingested"
        video.source_type = "video"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?source_type=video"))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["source_documents"]) == 1
        assert body["source_documents"][0]["id"] == str(video.id)
        assert body["source_documents"][0]["source_type"] == "video"
        assert body["total_source_documents"] == 1

    async def test_multiple_source_types(self, client: AsyncClient, db_session: AsyncSession) -> None:
        pdf = await _seed_source_document(db_session, title="pdf-doc", original_filename="guide.pdf")
        pdf.status = "ingested"
        video = await _seed_source_document(db_session, title="video-doc", original_filename="clip.mp4")
        video.status = "ingested"
        video.source_type = "video"
        audio = await _seed_source_document(db_session, title="audio-doc", original_filename="clip.mp3")
        audio.status = "ingested"
        audio.source_type = "audio"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?source_type=video&source_type=audio"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["source_type"] for row in body["source_documents"]} == {"video", "audio"}
        assert body["total_source_documents"] == 2

        resp = await client.get(platform_path("/admin/source-documents?source_type=video,audio"))
        assert resp.status_code == 200
        assert resp.json()["total_source_documents"] == 2

    async def test_invalid_source_type_rejected(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/source-documents?source_type=avi"))
        assert resp.status_code == 422

        resp = await client.get(platform_path("/admin/source-documents?source_type=video&source_type=avi"))
        assert resp.status_code == 422

    async def test_filename_query(self, client: AsyncClient, db_session: AsyncSession) -> None:
        match = await _seed_source_document(
            db_session,
            title="other-title",
            original_filename="Hypertension_Training.mp4",
        )
        match.status = "ingested"
        match.source_type = "video"
        miss = await _seed_source_document(
            db_session,
            title="unrelated",
            original_filename="Diabetes_Overview.mp4",
        )
        miss.status = "ingested"
        miss.source_type = "video"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?source_type=video&q=hyper"))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["source_documents"]) == 1
        assert body["source_documents"][0]["original_filename"] == "Hypertension_Training.mp4"
        assert body["total_source_documents"] == 1

    async def test_filename_query_matches_title(self, client: AsyncClient, db_session: AsyncSession) -> None:
        doc = await _seed_source_document(
            db_session,
            title="BRAC Counselling Video",
            original_filename="clip-001.mp4",
        )
        doc.status = "ingested"
        doc.source_type = "video"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?source_type=video&q=counselling"))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["source_documents"]) == 1
        assert body["source_documents"][0]["title"] == "BRAC Counselling Video"

    async def test_pagination(self, client: AsyncClient, db_session: AsyncSession) -> None:
        for i in range(3):
            doc = await _seed_source_document(db_session, title=f"doc-{i}")
            doc.status = "ingested"
            doc.ingested_at = datetime.now(UTC) + timedelta(seconds=i)
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?limit=2&offset=0"))
        body = resp.json()
        assert len(body["source_documents"]) == 2
        assert body["total_source_documents"] == 3
        assert body["total_pages"] == 2
        assert body["limit"] == 2
        assert body["offset"] == 0

        resp = await client.get(platform_path("/admin/source-documents?limit=2&offset=2"))
        body = resp.json()
        assert len(body["source_documents"]) == 1
        assert body["total_source_documents"] == 3
        assert body["total_pages"] == 2
        assert body["offset"] == 2

    async def test_sort_by_validation_rejects_invalid(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/source-documents?sort_by=invalid"))
        assert resp.status_code == 422

    async def test_sort_dir_validation_rejects_invalid(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/admin/source-documents?sort_dir=up"))
        assert resp.status_code == 422

    async def test_list_orders_by_title_asc(self, client: AsyncClient, db_session: AsyncSession) -> None:
        alpha = await _seed_source_document(db_session, title="alpha-doc")
        alpha.status = "ingested"
        beta = await _seed_source_document(db_session, title="beta-doc")
        beta.status = "ingested"
        gamma = await _seed_source_document(db_session, title="gamma-doc")
        gamma.status = "ingested"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?sort_by=title&sort_dir=asc"))
        titles = [row["title"] for row in resp.json()["source_documents"]]
        assert titles == ["alpha-doc", "beta-doc", "gamma-doc"]

    async def test_list_orders_by_ingested_at_asc(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        older = await _seed_source_document(db_session, title="older")
        older.status = "ingested"
        older.ingested_at = datetime.now(UTC) - timedelta(days=2)
        newer = await _seed_source_document(db_session, title="newer")
        newer.status = "ingested"
        newer.ingested_at = datetime.now(UTC)
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?sort_by=ingested_at&sort_dir=asc"))
        titles = [row["title"] for row in resp.json()["source_documents"]]
        assert titles == ["older", "newer"]

    async def test_list_orders_by_original_filename_nulls_last(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        with_name = await _seed_source_document(
            db_session,
            title="named",
            original_filename="alpha.pdf",
        )
        with_name.status = "ingested"
        without_name = await _seed_source_document(
            db_session,
            title="unnamed",
            original_filename=None,
        )
        without_name.status = "ingested"
        await db_session.commit()

        resp = await client.get(
            platform_path("/admin/source-documents?sort_by=original_filename&sort_dir=asc")
        )
        ids = [row["id"] for row in resp.json()["source_documents"]]
        assert ids == [str(with_name.id), str(without_name.id)]

        resp = await client.get(
            platform_path("/admin/source-documents?sort_by=original_filename&sort_dir=desc")
        )
        ids = [row["id"] for row in resp.json()["source_documents"]]
        assert ids == [str(with_name.id), str(without_name.id)]

    async def test_default_excludes_retired(self, client: AsyncClient, db_session: AsyncSession) -> None:
        active = await _seed_source_document(db_session, title="active-doc")
        active.status = "ingested"
        retired = await _seed_source_document(db_session, title="retired-doc", sync_published_visible=True)
        retired.status = "retired"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"active-doc"}
        assert body["total_source_documents"] == 1

    async def test_status_filter_retired(self, client: AsyncClient, db_session: AsyncSession) -> None:
        active = await _seed_source_document(db_session, title="active-doc")
        active.status = "ingested"
        retired = await _seed_source_document(db_session, title="retired-doc", sync_published_visible=True)
        retired.status = "retired"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?status=retired"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"retired-doc"}
        assert body["total_source_documents"] == 1

    async def test_sync_published_visible_true_excludes_retired(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        knowledge = await _seed_source_document(
            db_session, title="knowledge-active", sync_published_visible=True
        )
        knowledge.status = "uploaded"
        knowledge_retired = await _seed_source_document(
            db_session, title="knowledge-retired", sync_published_visible=True
        )
        knowledge_retired.status = "retired"
        ingest = await _seed_source_document(db_session, title="ingest-doc", sync_published_visible=False)
        ingest.status = "ingested"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?sync_published_visible=true"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"knowledge-active"}
        assert body["total_source_documents"] == 1

    async def test_sync_published_visible_false(self, client: AsyncClient, db_session: AsyncSession) -> None:
        knowledge = await _seed_source_document(
            db_session, title="knowledge-doc", sync_published_visible=True
        )
        knowledge.status = "uploaded"
        ingest = await _seed_source_document(db_session, title="ingest-doc", sync_published_visible=False)
        ingest.status = "ingested"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?sync_published_visible=false"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"ingest-doc"}
        assert body["total_source_documents"] == 1

    async def test_omit_sync_published_visible_returns_both(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        knowledge = await _seed_source_document(
            db_session, title="knowledge-doc", sync_published_visible=True
        )
        knowledge.status = "uploaded"
        ingest = await _seed_source_document(db_session, title="ingest-doc", sync_published_visible=False)
        ingest.status = "ingested"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"knowledge-doc", "ingest-doc"}
        assert body["total_source_documents"] == 2

    async def test_sync_published_visible_true_and_status_retired(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        knowledge_active = await _seed_source_document(
            db_session, title="knowledge-active", sync_published_visible=True
        )
        knowledge_active.status = "uploaded"
        knowledge_retired = await _seed_source_document(
            db_session, title="knowledge-retired", sync_published_visible=True
        )
        knowledge_retired.status = "retired"
        # Ingest docs cannot normally be retired via the API, but the filter
        # combination should still only return retired knowledge rows.
        ingest_retired = await _seed_source_document(
            db_session, title="ingest-retired", sync_published_visible=False
        )
        ingest_retired.status = "retired"
        await db_session.commit()

        resp = await client.get(
            platform_path("/admin/source-documents?sync_published_visible=true&status=retired")
        )
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"knowledge-retired"}
        assert body["total_source_documents"] == 1

    async def test_list_includes_stored_path(self, client: AsyncClient, db_session: AsyncSession) -> None:
        doc = await _seed_source_document(
            db_session,
            title="path-doc",
            storage_path="medtronics-storage/ingest/path-doc.pdf",
        )
        doc.status = "ingested"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents"))
        assert resp.status_code == 200
        row = resp.json()["source_documents"][0]
        assert row["stored_path"] == "medtronics-storage/ingest/path-doc.pdf"


class TestSourceDocumentMetadata:
    async def test_list_includes_description_and_thumbnail(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        doc = await _seed_source_document(db_session, title="meta-doc")
        doc.status = "ingested"
        doc.description = "A short blurb"
        doc.thumbnail_storage_path = "medtronics-storage/ingest/thumbnails/x.png"
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents"))
        assert resp.status_code == 200
        row = resp.json()["source_documents"][0]
        assert row["description"] == "A short blurb"
        assert row["thumbnail_storage_path"] == "medtronics-storage/ingest/thumbnails/x.png"
        assert row["stored_path"] == doc.original_storage_path
        assert row["duration_ms"] is None

    async def test_list_includes_duration_ms_for_video(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        pdf = await _seed_source_document(db_session, title="pdf-doc")
        pdf.status = "ingested"
        video = await _seed_source_document(db_session, title="video-doc", original_filename="clip.mp4")
        video.status = "ingested"
        video.source_type = "video"
        video.duration_ms = 90_000
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents?source_type=video"))
        assert resp.status_code == 200
        rows = resp.json()["source_documents"]
        assert len(rows) == 1
        assert rows[0]["title"] == "video-doc"
        assert rows[0]["duration_ms"] == 90_000

    async def test_patch_title_and_description(self, client: AsyncClient, db_session: AsyncSession) -> None:
        doc = await _seed_source_document(db_session, title="old-title")
        doc.status = "ingesting"
        await db_session.commit()

        resp = await client.patch(
            platform_path(f"/admin/source-documents/{doc.id}"),
            json={"title": "new-title", "description": "updated desc"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "new-title"
        assert body["description"] == "updated desc"
        assert body["status"] == "ingesting"

        await db_session.refresh(doc)
        assert doc.title == "new-title"
        assert doc.description == "updated desc"
        assert doc.status == "ingesting"

    async def test_patch_rejects_empty_title(self, client: AsyncClient, db_session: AsyncSession) -> None:
        doc = await _seed_source_document(db_session, title="keep")
        doc.status = "ingested"
        await db_session.commit()

        resp = await client.patch(
            platform_path(f"/admin/source-documents/{doc.id}"),
            json={"title": "   "},
        )
        assert resp.status_code == 422

    async def test_patch_does_not_create_ingestion_run(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        doc = await _seed_source_document(db_session, title="no-reingest")
        doc.status = "ingested"
        await db_session.commit()

        before = (await db_session.execute(select(func.count()).select_from(IngestionRun))).scalar_one()

        resp = await client.patch(
            platform_path(f"/admin/source-documents/{doc.id}"),
            json={"description": "still no ingest"},
        )
        assert resp.status_code == 200

        after = (await db_session.execute(select(func.count()).select_from(IngestionRun))).scalar_one()
        assert after == before

    async def test_put_thumbnail_stores_path(
        self, client: AsyncClient, db_session: AsyncSession, app
    ) -> None:
        doc = await _seed_source_document(db_session, title="thumb-doc")
        doc.status = "ingested"
        await db_session.commit()

        resp = await client.put(
            platform_path(f"/admin/source-documents/{doc.id}/thumbnail"),
            files={"file": ("thumb.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["thumbnail_storage_path"] == (f"medtronics-storage/ingest/thumbnails/{doc.id}.png")
        assert body["status"] == "ingested"

        fake = app.dependency_overrides[get_object_storage_client]()
        assert len(fake.put_calls) == 1
        assert fake.put_calls[0]["content_type"] == "image/png"

    async def test_put_thumbnail_rejects_invalid_content_type(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        doc = await _seed_source_document(db_session, title="bad-thumb")
        doc.status = "ingested"
        await db_session.commit()

        resp = await client.put(
            platform_path(f"/admin/source-documents/{doc.id}/thumbnail"),
            files={"file": ("thumb.gif", b"GIF89a", "image/gif")},
        )
        assert resp.status_code == 422


class TestUploadedDateFilteringAndSorting:
    async def test_uploaded_date_in_summary(self, client: AsyncClient, db_session: AsyncSession) -> None:
        doc = await _seed_source_document(db_session, title="summary-test")
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents"))
        assert resp.status_code == 200
        row = next(r for r in resp.json()["source_documents"] if r["id"] == str(doc.id))
        assert "uploaded_date" in row
        assert row["uploaded_date"] is not None

    async def test_uploaded_date_range_filter(self, client: AsyncClient, db_session: AsyncSession) -> None:
        base_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        doc1 = await _seed_source_document(db_session, title="doc-june-1")
        doc1.uploaded_date = base_time
        doc2 = await _seed_source_document(db_session, title="doc-june-15")
        doc2.uploaded_date = base_time + timedelta(days=14)
        doc3 = await _seed_source_document(db_session, title="doc-july-1")
        doc3.uploaded_date = base_time + timedelta(days=30)
        await db_session.commit()

        # Filter for June 10 to June 20
        from_str = (base_time + timedelta(days=9)).isoformat()
        to_str = (base_time + timedelta(days=19)).isoformat()
        resp = await client.get(
            platform_path(f"/admin/source-documents?uploaded_from={from_str}&uploaded_to={to_str}")
        )
        assert resp.status_code == 200
        titles = {row["title"] for row in resp.json()["source_documents"]}
        assert titles == {"doc-june-15"}

    async def test_uploaded_date_range_invalid(self, client: AsyncClient) -> None:
        from_str = datetime(2026, 6, 15, tzinfo=UTC).isoformat()
        to_str = datetime(2026, 6, 1, tzinfo=UTC).isoformat()
        resp = await client.get(
            platform_path(f"/admin/source-documents?uploaded_from={from_str}&uploaded_to={to_str}")
        )
        assert resp.status_code == 422
        assert "uploaded_from must be on or before uploaded_to" in resp.json()["detail"]

    async def test_sort_by_uploaded_date(self, client: AsyncClient, db_session: AsyncSession) -> None:
        t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        d1 = await _seed_source_document(db_session, title="first")
        d1.uploaded_date = t0
        d2 = await _seed_source_document(db_session, title="second")
        d2.uploaded_date = t0 + timedelta(days=1)
        await db_session.commit()

        resp_asc = await client.get(
            platform_path("/admin/source-documents?sort_by=uploaded_date&sort_dir=asc")
        )
        assert resp_asc.status_code == 200
        titles_asc = [
            r["title"] for r in resp_asc.json()["source_documents"] if r["title"] in ("first", "second")
        ]
        assert titles_asc == ["first", "second"]

        resp_desc = await client.get(
            platform_path("/admin/source-documents?sort_by=uploaded_date&sort_dir=desc")
        )
        assert resp_desc.status_code == 200
        titles_desc = [
            r["title"] for r in resp_desc.json()["source_documents"] if r["title"] in ("first", "second")
        ]
        assert titles_desc == ["second", "first"]


class TestListSourceDocumentsActorsAndAssigned:
    async def test_list_includes_actor_and_assigned_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        hierarchy = await seed_basic_hierarchy(db_session, tenant_id=1)
        assigned_doc = await _seed_source_document(db_session, title="assigned-doc")
        assigned_doc.status = "ingested"
        assigned_doc.uploaded_by = hierarchy.am_id
        assigned_doc.updated_by = hierarchy.sk_id
        assigned_doc.ingested_by = hierarchy.po_id
        unassigned_doc = await _seed_source_document(db_session, title="unassigned-doc")
        unassigned_doc.status = "ingested"
        unassigned_doc.uploaded_by = 999_999  # no matching users row
        unassigned_doc.ingested_by = 888_888  # no matching users row
        orphan_id_doc = await _seed_source_document(db_session, title="no-actors")
        orphan_id_doc.status = "ingested"
        db_session.add(
            DocumentAssignment(
                source_document_id=assigned_doc.id,
                user_id=hierarchy.sk_id,
                assigned_by=hierarchy.am_id,
                tenant_id=1,
            )
        )
        await db_session.commit()

        resp = await client.get(platform_path("/admin/source-documents"))
        assert resp.status_code == 200
        by_title = {row["title"]: row for row in resp.json()["source_documents"]}

        assigned_row = by_title["assigned-doc"]
        assert assigned_row["assigned"] is True
        assert assigned_row["uploaded_by"] == {"id": AM_ID, "name": "Test Area Manager"}
        assert assigned_row["updated_by"] == {"id": SK_ID, "name": "Test Shastiya Kormi"}
        assert assigned_row["ingested_by"] == {"id": PO_ID, "name": "Test PO"}

        unassigned_row = by_title["unassigned-doc"]
        assert unassigned_row["assigned"] is False
        assert unassigned_row["uploaded_by"] is None
        assert unassigned_row["updated_by"] is None
        assert unassigned_row["ingested_by"] is None

        bare_row = by_title["no-actors"]
        assert bare_row["assigned"] is False
        assert bare_row["uploaded_by"] is None
        assert bare_row["updated_by"] is None
        assert bare_row["ingested_by"] is None

    async def test_patch_metadata_sets_updated_by(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        hierarchy = await seed_basic_hierarchy(db_session, tenant_id=1)
        doc = await _seed_source_document(db_session, title="patch-me")
        doc.status = "ingested"
        await db_session.commit()

        patch = await client.patch(
            platform_path(f"/admin/source-documents/{doc.id}"),
            json={"title": "patched-title"},
            headers={"x-mock-user-id": str(hierarchy.am_id)},
        )
        assert patch.status_code == 200
        assert patch.json()["title"] == "patched-title"

        listed = await client.get(platform_path("/admin/source-documents"))
        assert listed.status_code == 200
        row = next(r for r in listed.json()["source_documents"] if r["id"] == str(doc.id))
        assert row["updated_by"] == {"id": AM_ID, "name": "Test Area Manager"}
        assert row["assigned"] is False


class TestListSourceDocumentsUploadedByAndAssignedFilters:
    async def _seed_filter_docs(self, db_session: AsyncSession):
        hierarchy = await seed_basic_hierarchy(db_session, tenant_id=1)
        am_doc = await _seed_source_document(db_session, title="am-uploaded")
        am_doc.status = "ingested"
        am_doc.uploaded_by = hierarchy.am_id
        po_doc = await _seed_source_document(db_session, title="po-uploaded")
        po_doc.status = "ingested"
        po_doc.uploaded_by = hierarchy.po_id
        assigned_doc = await _seed_source_document(db_session, title="assigned-ingested")
        assigned_doc.status = "ingested"
        assigned_doc.uploaded_by = hierarchy.am_id
        uploaded_assigned = await _seed_source_document(db_session, title="assigned-uploaded")
        uploaded_assigned.status = "uploaded"
        uploaded_assigned.uploaded_by = hierarchy.po_id
        bare = await _seed_source_document(db_session, title="no-uploader")
        bare.status = "ingested"
        db_session.add(
            DocumentAssignment(
                source_document_id=assigned_doc.id,
                user_id=hierarchy.sk_id,
                assigned_by=hierarchy.am_id,
                tenant_id=1,
            )
        )
        db_session.add(
            DocumentAssignment(
                source_document_id=uploaded_assigned.id,
                user_id=hierarchy.sk_id,
                assigned_by=hierarchy.am_id,
                tenant_id=1,
            )
        )
        await db_session.commit()
        return hierarchy

    async def test_uploaded_by_single(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_filter_docs(db_session)

        resp = await client.get(platform_path(f"/admin/source-documents?uploaded_by={AM_ID}"))
        assert resp.status_code == 200
        body = resp.json()
        titles = {row["title"] for row in body["source_documents"]}
        assert titles == {"am-uploaded", "assigned-ingested"}
        assert body["total_source_documents"] == 2

    async def test_uploaded_by_multi_csv_and_repeated(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await self._seed_filter_docs(db_session)

        csv_resp = await client.get(platform_path(f"/admin/source-documents?uploaded_by={AM_ID},{PO_ID}"))
        assert csv_resp.status_code == 200
        csv_titles = {row["title"] for row in csv_resp.json()["source_documents"]}
        assert csv_titles == {
            "am-uploaded",
            "po-uploaded",
            "assigned-ingested",
            "assigned-uploaded",
        }
        assert csv_resp.json()["total_source_documents"] == 4

        repeated = await client.get(
            platform_path(f"/admin/source-documents?uploaded_by={AM_ID}&uploaded_by={PO_ID}")
        )
        assert repeated.status_code == 200
        assert {row["title"] for row in repeated.json()["source_documents"]} == csv_titles

    async def test_uploaded_by_unknown_returns_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await self._seed_filter_docs(db_session)

        resp = await client.get(platform_path("/admin/source-documents?uploaded_by=999999"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["source_documents"] == []
        assert body["total_source_documents"] == 0

    async def test_uploaded_by_invalid_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.get(platform_path("/admin/source-documents?uploaded_by=abc"))
        assert resp.status_code == 422

    async def test_assigned_true(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_filter_docs(db_session)

        resp = await client.get(platform_path("/admin/source-documents?assigned=true"))
        assert resp.status_code == 200
        body = resp.json()
        titles = {row["title"] for row in body["source_documents"]}
        assert titles == {"assigned-ingested", "assigned-uploaded"}
        assert all(row["assigned"] is True for row in body["source_documents"])
        assert body["total_source_documents"] == 2

    async def test_assigned_false(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_filter_docs(db_session)

        resp = await client.get(platform_path("/admin/source-documents?assigned=false"))
        assert resp.status_code == 200
        body = resp.json()
        titles = {row["title"] for row in body["source_documents"]}
        assert titles == {"am-uploaded", "po-uploaded", "no-uploader"}
        assert all(row["assigned"] is False for row in body["source_documents"])
        assert body["total_source_documents"] == 3

    async def test_assigned_and_status_combine(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_filter_docs(db_session)

        resp = await client.get(platform_path("/admin/source-documents?assigned=true&status=ingested"))
        assert resp.status_code == 200
        body = resp.json()
        assert {row["title"] for row in body["source_documents"]} == {"assigned-ingested"}
        assert body["total_source_documents"] == 1
