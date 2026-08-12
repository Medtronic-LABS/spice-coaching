"""Admin knowledge uploaders list API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_foundation.problem import register_problem_handlers
from platform_service.api.knowledge import router as knowledge_router
from platform_service.auth.tenant_context import DEFAULT_SELECTED_TENANT_ID
from platform_service.config import get_settings
from platform_service.db.models.source_document import SourceDocument
from platform_service.deps import get_db, get_object_storage_client
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import platform_path, requires_db
from tests.helpers.hierarchy_fixtures import HIERARCHY_TRUNCATE_SQL, seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]

_BUCKET = "medtronics-storage"
_OTHER_TENANT_ID = 99


@pytest_asyncio.fixture(autouse=True)
async def _wipe_tables(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(text("TRUNCATE source_document RESTART IDENTITY CASCADE"))
    await db_session.execute(text(HIERARCHY_TRUNCATE_SQL))
    await db_session.commit()


@pytest_asyncio.fixture
async def storage_mock() -> MagicMock:
    storage = MagicMock()
    storage.bucket_name = _BUCKET
    return storage


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    storage_mock: MagicMock,
) -> AsyncIterator[AsyncClient]:
    app_obj = FastAPI()
    register_problem_handlers(
        app_obj,
        validation_error_type=RequestValidationError,
        http_exception_type=HTTPException,
    )
    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(knowledge_router)
    app_obj.include_router(api_router)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app_obj.dependency_overrides[get_db] = _override_get_db
    app_obj.dependency_overrides[get_object_storage_client] = lambda: storage_mock

    transport = ASGITransport(app=app_obj)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app_obj.dependency_overrides.clear()


async def _seed_doc(
    session: AsyncSession,
    *,
    uploaded_by: int | None,
    sync_published_visible: bool = True,
    status: str = "uploaded",
    tenant_id: int = DEFAULT_SELECTED_TENANT_ID,
    title: str = "Knowledge doc",
) -> SourceDocument:
    doc = SourceDocument(
        title=title,
        source_type="pdf",
        primary_language="bn",
        content_domain="clinical",
        original_storage_path=f"{_BUCKET}/source-documents/knowledge/{uuid4()}.pdf",
        original_filename="manual.pdf",
        sync_published_visible=sync_published_visible,
        status=status,
        uploaded_by=uploaded_by,
        tenant_id=tenant_id,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def _list_uploaders(client: AsyncClient) -> Any:
    return await client.get(platform_path("/admin/knowledge/uploaders"))


class TestKnowledgeUploaders:
    async def test_empty_when_no_knowledge_docs(self, client: AsyncClient) -> None:
        resp = await _list_uploaders(client)
        assert resp.status_code == 200
        assert resp.json() == {"uploaders": []}

    async def test_dedupes_same_uploader(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=DEFAULT_SELECTED_TENANT_ID)
        await db_session.commit()
        await _seed_doc(db_session, uploaded_by=seed.am_id, title="Doc A")
        await _seed_doc(db_session, uploaded_by=seed.am_id, title="Doc B")

        resp = await _list_uploaders(client)
        assert resp.status_code == 200
        assert resp.json() == {"uploaders": [{"id": seed.am_id, "name": "Test Area Manager"}]}

    async def test_sorted_by_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=DEFAULT_SELECTED_TENANT_ID)
        await db_session.commit()
        await _seed_doc(db_session, uploaded_by=seed.am_id)
        await _seed_doc(db_session, uploaded_by=seed.po_other_id)

        resp = await _list_uploaders(client)
        assert resp.status_code == 200
        assert resp.json() == {
            "uploaders": [
                {"id": seed.po_other_id, "name": "Other PO"},
                {"id": seed.am_id, "name": "Test Area Manager"},
            ]
        }

    async def test_excludes_null_uploaded_by(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=DEFAULT_SELECTED_TENANT_ID)
        await db_session.commit()
        await _seed_doc(db_session, uploaded_by=None)
        await _seed_doc(db_session, uploaded_by=seed.po_id)

        resp = await _list_uploaders(client)
        assert resp.status_code == 200
        assert resp.json() == {"uploaders": [{"id": seed.po_id, "name": "Test PO"}]}

    async def test_excludes_retired_knowledge(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=DEFAULT_SELECTED_TENANT_ID)
        await db_session.commit()
        await _seed_doc(db_session, uploaded_by=seed.am_id, status="retired")
        await _seed_doc(db_session, uploaded_by=seed.po_id, status="uploaded")

        resp = await _list_uploaders(client)
        assert resp.status_code == 200
        assert resp.json() == {"uploaders": [{"id": seed.po_id, "name": "Test PO"}]}

    async def test_excludes_non_knowledge(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=DEFAULT_SELECTED_TENANT_ID)
        await db_session.commit()
        await _seed_doc(db_session, uploaded_by=seed.am_id, sync_published_visible=False)
        await _seed_doc(db_session, uploaded_by=seed.sk_id, sync_published_visible=True)

        resp = await _list_uploaders(client)
        assert resp.status_code == 200
        assert resp.json() == {"uploaders": [{"id": seed.sk_id, "name": "Test Shastiya Kormi"}]}

    async def test_excludes_other_tenant(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        selected = await seed_basic_hierarchy(db_session, tenant_id=DEFAULT_SELECTED_TENANT_ID)
        other = await seed_basic_hierarchy(
            db_session,
            tenant_id=_OTHER_TENANT_ID,
            district_name="Other District",
            upazila_name="Other Upazila",
            upazila_other_name="Other Upazila 2",
            am_id=9101,
            po_id=9201,
            po_other_id=9202,
            sk_id=9301,
            sk_other_id=9302,
        )
        await db_session.commit()
        await _seed_doc(db_session, uploaded_by=other.am_id, tenant_id=_OTHER_TENANT_ID)
        await _seed_doc(db_session, uploaded_by=selected.po_id, tenant_id=DEFAULT_SELECTED_TENANT_ID)

        resp = await _list_uploaders(client)
        assert resp.status_code == 200
        assert resp.json() == {"uploaders": [{"id": selected.po_id, "name": "Test PO"}]}

    async def test_excludes_unresolved_hierarchy_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=DEFAULT_SELECTED_TENANT_ID)
        await db_session.commit()
        await _seed_doc(db_session, uploaded_by=999_999)
        await _seed_doc(db_session, uploaded_by=seed.am_id)

        resp = await _list_uploaders(client)
        assert resp.status_code == 200
        assert resp.json() == {"uploaders": [{"id": seed.am_id, "name": "Test Area Manager"}]}
