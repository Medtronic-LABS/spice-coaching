"""API integration tests for GET /sync/video-progress."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from platform_service.api.sync import router as sync_router
from platform_service.auth.spice_identity import SYNC_AUTH_DISABLED_DEFAULT_USER_ID
from platform_service.config import get_settings
from platform_service.db.models.document_assignment import DocumentAssignment
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.repositories.video_progress_repository import VideoProgressRepository
from platform_service.deps import get_db
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import platform_path, requires_db
from tests.helpers.hierarchy_fixtures import seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]

_TENANT_ID = 1


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data_between_tests(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text(
            "TRUNCATE chw_video_progress, document_assignment, source_document, "
            "users, upazila, district RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    app_obj = FastAPI()

    @app_obj.middleware("http")
    async def inject_tenant(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.selected_tenant_id = int(request.headers.get("x-mock-tenant-id", "1"))
        mock_user_id = request.headers.get("x-mock-user-id")
        if mock_user_id:
            request.state.spice_user = type("U", (), {"id": int(mock_user_id)})()
        return await call_next(request)

    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(sync_router)
    app_obj.include_router(api_router)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app_obj.dependency_overrides[get_db] = _override_get_db
    yield app_obj
    app_obj.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed_video(session: AsyncSession, *, title: str = "video") -> SourceDocument:
    doc = SourceDocument(
        title=title,
        source_type="video",
        primary_language="bn",
        content_domain="clinical",
        original_storage_path=f"medtronics-storage/ingest/{uuid4()}.mp4",
        original_filename="clip.mp4",
        status="ingested",
        tenant_id=_TENANT_ID,
    )
    session.add(doc)
    await session.flush()
    return doc


class TestSyncVideoProgressApi:
    async def test_requires_since(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/sync/video-progress"))
        assert resp.status_code == 422

    async def test_returns_progress_for_default_user(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, sk_id=SYNC_AUTH_DISABLED_DEFAULT_USER_ID)
        doc = await _seed_video(db_session)
        db_session.add(
            DocumentAssignment(
                id=uuid4(),
                source_document_id=doc.id,
                user_id=seed.sk_id,
                assigned_by=seed.sk_id,
                tenant_id=_TENANT_ID,
            )
        )
        await VideoProgressRepository(db_session).upsert(
            chw_id=seed.sk_id,
            source_document_id=doc.id,
            last_position_ms=9_000,
            percent_watched=55.0,
            completed=True,
            tenant_id=_TENANT_ID,
        )
        await db_session.commit()

        since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        resp = await client.get(
            platform_path("/sync/video-progress"),
            params={"since": since},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "server_time_utc" in data
        assert len(data["videos"]) == 1
        video = data["videos"][0]
        assert video["source_document_id"] == str(doc.id)
        assert video["last_position_ms"] == 9_000
        assert video["percent_watched"] == 55.0
        assert video["completed"] is True
        assert video["last_watched_at"] is not None

    async def test_omits_revoked_assignment(self, client: AsyncClient, db_session: AsyncSession) -> None:
        seed = await seed_basic_hierarchy(db_session, sk_id=SYNC_AUTH_DISABLED_DEFAULT_USER_ID)
        doc = await _seed_video(db_session)
        await VideoProgressRepository(db_session).upsert(
            chw_id=seed.sk_id,
            source_document_id=doc.id,
            last_position_ms=1_000,
            percent_watched=10.0,
            completed=False,
            tenant_id=_TENANT_ID,
        )
        await db_session.commit()

        since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        resp = await client.get(
            platform_path("/sync/video-progress"),
            params={"since": since},
        )
        assert resp.status_code == 200
        assert resp.json()["videos"] == []

    async def test_omits_non_video_assignment(self, client: AsyncClient, db_session: AsyncSession) -> None:
        seed = await seed_basic_hierarchy(db_session, sk_id=SYNC_AUTH_DISABLED_DEFAULT_USER_ID)
        doc = SourceDocument(
            title="pdf-assigned",
            source_type="pdf",
            primary_language="bn",
            content_domain="clinical",
            original_storage_path=f"medtronics-storage/ingest/{uuid4()}.pdf",
            original_filename="doc.pdf",
            status="ingested",
            tenant_id=_TENANT_ID,
        )
        db_session.add(doc)
        await db_session.flush()
        db_session.add(
            DocumentAssignment(
                id=uuid4(),
                source_document_id=doc.id,
                user_id=seed.sk_id,
                assigned_by=seed.sk_id,
                tenant_id=_TENANT_ID,
            )
        )
        await VideoProgressRepository(db_session).upsert(
            chw_id=seed.sk_id,
            source_document_id=doc.id,
            last_position_ms=500,
            percent_watched=5.0,
            completed=False,
            tenant_id=_TENANT_ID,
        )
        await db_session.commit()

        since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        resp = await client.get(
            platform_path("/sync/video-progress"),
            params={"since": since},
        )
        assert resp.status_code == 200
        assert resp.json()["videos"] == []

    async def test_respects_mock_user_header(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
        get_settings.cache_clear()

        seed = await seed_basic_hierarchy(db_session)
        doc = await _seed_video(db_session)
        db_session.add(
            DocumentAssignment(
                id=uuid4(),
                source_document_id=doc.id,
                user_id=seed.sk_id,
                assigned_by=seed.sk_id,
                tenant_id=_TENANT_ID,
            )
        )
        await VideoProgressRepository(db_session).upsert(
            chw_id=seed.sk_id,
            source_document_id=doc.id,
            last_position_ms=3_000,
            percent_watched=15.0,
            completed=False,
            tenant_id=_TENANT_ID,
        )
        await db_session.commit()

        since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        resp = await client.get(
            platform_path("/sync/video-progress"),
            params={"since": since},
            headers={"x-mock-user-id": str(seed.sk_id)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["videos"]) == 1

        other = await client.get(
            platform_path("/sync/video-progress"),
            params={"since": since},
            headers={"x-mock-user-id": str(seed.sk_other_id)},
        )
        assert other.status_code == 200
        assert other.json()["videos"] == []

        get_settings.cache_clear()
