"""Device sync route smoke tests."""

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
from platform_service.db.models.module_card import ModuleCard
from platform_service.deps import get_db, get_object_storage_client
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import (
    _mock_storage,
    _seed_module,
    _seed_source_document,
    _unit_basis_vector,
)
from tests.conftest import platform_path, requires_db
from tests.helpers.hierarchy_fixtures import seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data_between_tests(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text(
            "TRUNCATE module_quiz_question, module, module_family, "
            "document_assignment, content_block, source_page, source_document, "
            "config_threshold_change, config_threshold, "
            "users, upazila, district "
            "RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()


class _FakeStorage:
    bucket_name = "medtronics-storage"
    allowed_prefixes = frozenset({"uploads", "source-documents"})

    async def presigned_get_url(self, **kwargs):  # type: ignore[no-untyped-def]
        return type("Url", (), {"url": "https://example.test/obj", "expires_at": datetime.now(UTC)})()


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
    app_obj.dependency_overrides[get_object_storage_client] = lambda: _FakeStorage()
    yield app_obj
    app_obj.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSyncRoutes:
    async def test_config_sync_returns_bundle(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/sync/config"))
        assert resp.status_code == 200
        data = resp.json()
        assert "thresholds" in data
        assert "locales" in data
        locales = data["locales"]
        settings = get_settings()
        assert locales["primary"] == settings.deployment_primary_locale
        assert "mirror" not in locales
        assert locales["supported"] == settings.deployment_locale_config.supported

    async def test_config_sync_returns_selected_tenant_latest_values(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Unscoped sync used to collapse keys across tenants and return stale values."""
        key = "quiz_reattempt_validity_days"
        await db_session.execute(
            text(
                """
                INSERT INTO config_threshold (tenant_id, key, title, description) VALUES
                (1, :key, 'Tenant A', 'A'),
                (2, :key, 'Tenant B', 'B')
                """
            ),
            {"key": key},
        )
        await db_session.execute(
            text(
                """
                INSERT INTO config_threshold_change (
                    tenant_id, config_threshold_id, key,
                    previous_value_json, current_value_json, version, updated_by
                )
                SELECT ct.tenant_id, ct.id, ct.key, NULL, '7'::jsonb, 1, 'seed'
                FROM config_threshold AS ct
                WHERE ct.key = :key AND ct.tenant_id IN (1, 2)
                """
            ),
            {"key": key},
        )
        await db_session.execute(
            text(
                """
                INSERT INTO config_threshold_change (
                    tenant_id, config_threshold_id, key,
                    previous_value_json, current_value_json, version, updated_by
                )
                SELECT ct.tenant_id, ct.id, ct.key, '7'::jsonb, '45'::jsonb, 2, 'admin'
                FROM config_threshold AS ct
                WHERE ct.key = :key AND ct.tenant_id = 1
                """
            ),
            {"key": key},
        )
        await db_session.commit()

        resp_a = await client.get(
            platform_path("/sync/config"),
            headers={"x-mock-tenant-id": "1"},
        )
        assert resp_a.status_code == 200
        assert resp_a.json()["thresholds"][key] == 45

        resp_b = await client.get(
            platform_path("/sync/config"),
            headers={"x-mock-tenant-id": "2"},
        )
        assert resp_b.status_code == 200
        assert resp_b.json()["thresholds"][key] == 7

    async def test_modules_sync_requires_since(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/sync/modules"))
        assert resp.status_code == 422

    async def test_modules_sync_empty_when_no_updates(self, client: AsyncClient) -> None:
        since = datetime.now(UTC).isoformat()
        resp = await client.get(platform_path("/sync/modules"), params={"since": since})
        assert resp.status_code == 200
        data = resp.json()
        assert data["modules"] == []
        assert data["assigned_module_ids"] == []
        assert data["requested_modules"] == []


class TestCardEmbeddingsSync:
    async def test_requires_since(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/sync/card-embeddings"))
        assert resp.status_code == 422

    async def test_empty_when_no_updates(self, client: AsyncClient) -> None:
        since = datetime.now(UTC).isoformat()
        resp = await client.get(platform_path("/sync/card-embeddings"), params={"since": since})
        assert resp.status_code == 200
        data = resp.json()
        assert data["cards"] == []
        assert data["embedding_dimension"] == get_settings().embedding_dimension
        assert "server_time_utc" in data

    async def test_returns_embeddings_for_updated_module(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        module = await _seed_module(
            db_session,
            module_json={
                "cards": [
                    {
                        "title": {"bn": "C1"},
                        "body": {"bn": "B1"},
                        "source_block_ids": [str(uuid4())],
                    }
                ]
            },
        )
        card = (
            await db_session.execute(select(ModuleCard).where(ModuleCard.module_id == module.id))
        ).scalar_one()
        card.local_embedding = _unit_basis_vector(0)
        await db_session.commit()

        since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        resp = await client.get(platform_path("/sync/card-embeddings"), params={"since": since})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["cards"]) == 1
        row = data["cards"][0]
        assert row["card_id"] == str(card.id)
        assert row["module_id"] == str(module.id)
        assert row["card_family_id"] == str(card.card_family_id)
        assert row["embedding"] == _unit_basis_vector(0)


class TestSourceDocumentsSync:
    async def test_requires_since(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/sync/source-documents"))
        assert resp.status_code == 422

    async def test_old_published_path_returns_404(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path("/sync/source-documents/published"))
        assert resp.status_code == 404

    async def test_returns_module_linked_documents(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        doc = await _seed_source_document(db_session, sync_published_visible=False)
        await _seed_module(db_session, source_document_ids=[doc.id])
        since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        resp = await client.get(
            platform_path("/sync/source-documents"),
            params={"since": since},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "server_time_utc" in data
        assert "missing_ids" not in data
        assert "modules" not in data
        assert len(data["source_documents"]) == 1
        entry = data["source_documents"][0]
        assert entry["source_document_id"] == str(doc.id)
        assert entry["title"] == doc.title
        assert entry["description"] is None
        assert entry["source_type"] == doc.source_type
        assert entry["assigned_at"] is None
        assert data["assigned_documents"] == []

    async def test_presigns_source_document_and_thumbnail(
        self, app: FastAPI, db_session: AsyncSession
    ) -> None:
        doc = await _seed_source_document(db_session, title="RMNCH Manual")
        doc.thumbnail_storage_path = "medtronics-storage/ingest/thumbnails/manual.png"
        await db_session.commit()
        await _seed_module(db_session, source_document_ids=[doc.id])

        thumb_url = "https://minio.example/thumb.png"
        mock_storage = _mock_storage(presigned_url=thumb_url)
        app.dependency_overrides[get_object_storage_client] = lambda: mock_storage

        since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                platform_path("/sync/source-documents"),
                params={"since": since},
            )

        assert resp.status_code == 200
        entry = resp.json()["source_documents"][0]
        assert entry["presigned_url"] == thumb_url
        assert entry["presigned_expires_seconds"] == get_settings().admin_file_presigned_max_seconds
        assert "thumbnail_storage_path" not in entry
        assert entry["thumbnail_presigned_url"] == thumb_url
        assert entry["thumbnail_presigned_expires_seconds"] == get_settings().admin_file_presigned_max_seconds

    async def test_returns_assigned_documents_for_default_user(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, sk_id=SYNC_AUTH_DISABLED_DEFAULT_USER_ID)
        doc = await _seed_source_document(db_session, title="Assigned video")
        db_session.add(
            DocumentAssignment(
                id=uuid4(),
                source_document_id=doc.id,
                user_id=seed.sk_id,
                assigned_by=seed.sk_id,
                tenant_id=1,
            )
        )
        await db_session.commit()
        since = datetime.now(UTC).isoformat()

        resp = await client.get(
            platform_path("/sync/source-documents"),
            params={"since": since},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_documents"] == []
        assert len(data["assigned_documents"]) == 1
        assert data["assigned_documents"][0]["source_document_id"] == str(doc.id)
        assert data["assigned_documents"][0]["source_type"] == doc.source_type
        assert data["assigned_documents"][0]["assigned_at"] is not None
