from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_foundation.problem import register_problem_handlers
from platform_service.api.assignments import router as assignments_router
from platform_service.api.sync import router as sync_router
from platform_service.config import Settings, get_settings
from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.models.source_document import SourceDocument
from platform_service.deps import get_db
from pydantic_settings import SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import platform_path, requires_db
from tests.helpers.hierarchy_fixtures import (
    AM_ID,
    PO_ID,
    PO_OTHER_ID,
    SK_ID,
    SK_OTHER_ID,
    seed_basic_hierarchy,
    seed_multi_district_hierarchy,
)

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def _enable_spice_auth(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setattr(
        Settings,
        "model_config",
        SettingsConfigDict(env_file=None, env_file_encoding="utf-8", extra="ignore"),
    )
    monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data_between_tests(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text(
            "TRUNCATE document_assignment, module_assignment, module, module_family, "
            "source_document, "
            '"users", district, upazila, user_upazila RESTART IDENTITY CASCADE'
        )
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> FastAPI:
    app_obj = FastAPI()
    register_problem_handlers(
        app_obj,
        validation_error_type=RequestValidationError,
        http_exception_type=HTTPException,
    )

    @app_obj.middleware("http")
    async def mock_auth_middleware(request: Request, call_next):
        mock_user_id = request.headers.get("x-mock-user-id")
        request.state.selected_tenant_id = 0
        if mock_user_id:

            class MockSpiceUser:
                id = int(mock_user_id)

            request.state.spice_user = MockSpiceUser()
        return await call_next(request)

    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(assignments_router)
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


async def _seed_module(session: AsyncSession, title: str, *, tenant_id: int = 1) -> Module:
    family = ModuleFamily(module_code=f"f-{uuid4().hex[:8]}", tenant_id=tenant_id)
    session.add(family)
    await session.flush()
    module = Module(
        module_family_id=family.id,
        version=1,
        title_localized={"bn": title, "en": title},
        domain="rmnch",
        module_type="refresher",
        lifecycle_status="published",
        module_json={"cards": [{"title": {"bn": "c"}}]},
        published_at=datetime.now(UTC),
        tenant_id=tenant_id,
    )
    session.add(module)
    await session.flush()
    family.current_published_module_id = module.id
    await session.flush()
    await session.commit()
    return module


async def _seed_source_document(
    session: AsyncSession, *, title: str = "Knowledge PDF", tenant_id: int = 1
) -> SourceDocument:
    doc = SourceDocument(
        title=title,
        source_type="pdf",
        primary_language="bn",
        content_domain="clinical",
        original_storage_path=f"medtronics-storage/knowledge/{uuid4().hex}.pdf",
        original_filename="manual.pdf",
        tenant_id=tenant_id,
    )
    session.add(doc)
    await session.flush()
    await session.commit()
    return doc


class TestAssignments:
    async def test_create_assignment_workflow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module_1 = await _seed_module(db_session, "Module One")
        module_2 = await _seed_module(db_session, "Module Two")

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module_1.id), "user_ids": [SK_ID, SK_OTHER_ID]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["assigned_count"] == 2
        assert len(data["assignment_ids"]) == 2

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module_1.id), "user_ids": [SK_ID, PO_OTHER_ID]},
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 2  # SK_ID existing, PO_OTHER_ID new

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module_2.id), "user_ids": [PO_ID]},
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 1  # PO only by default

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={
                "module_id": str(module_2.id),
                "user_ids": [PO_ID],
                "expand_po_assignees": True,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 2  # PO + SK under PO when expanded

    async def test_sync_filtering_by_direct_assignment(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module_1 = await _seed_module(db_session, "Module One")
        await _seed_module(db_session, "Module Two")
        await _seed_module(db_session, "Module Three")

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module_1.id), "user_ids": [SK_ID]},
        )

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(SK_OTHER_ID)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["modules"]) == 3
        assert resp.json()["assigned_module_ids"] == []

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(SK_ID)},
        )
        assert resp.status_code == 200
        assigned_module_ids = resp.json()["assigned_module_ids"]
        assert len(assigned_module_ids) == 1
        assert assigned_module_ids[0]["module_id"] == str(module_1.id)
        assert assigned_module_ids[0]["assigned_at"] is not None

    async def test_sync_filtering_by_po_assignment(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module_1 = await _seed_module(db_session, "PO Assigned Module")

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module_1.id), "user_ids": [PO_ID]},
        )

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(SK_ID)},
        )
        assert resp.status_code == 200
        assert resp.json()["assigned_module_ids"] == []

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(PO_ID)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["assigned_module_ids"]) == 1

    async def test_sync_filtering_by_po_assignment_expanded(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module_1 = await _seed_module(db_session, "PO Expanded Module")

        await client.post(
            platform_path("/admin/assignments"),
            json={
                "module_id": str(module_1.id),
                "user_ids": [PO_ID],
                "expand_po_assignees": True,
            },
        )

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(SK_ID)},
        )
        assert resp.status_code == 200
        assigned_module_ids = resp.json()["assigned_module_ids"]
        assert len(assigned_module_ids) == 1
        assert assigned_module_ids[0]["module_id"] == str(module_1.id)
        assert assigned_module_ids[0]["assigned_at"] is not None

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(PO_ID)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["assigned_module_ids"]) == 1

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(SK_OTHER_ID)},
        )
        assert resp.status_code == 200
        assert resp.json()["assigned_module_ids"] == []

    async def test_sync_sk_assignment_does_not_include_po(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module_1 = await _seed_module(db_session, "SK Only Module")

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module_1.id), "user_ids": [SK_ID]},
        )

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(SK_ID)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["assigned_module_ids"]) == 1

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(PO_ID)},
        )
        assert resp.status_code == 200
        assert resp.json()["assigned_module_ids"] == []

    async def test_sync_filtering_geographical(self, client: AsyncClient, db_session: AsyncSession) -> None:
        hierarchy = await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module_1 = await _seed_module(db_session, "Geo Module")

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module_1.id), "upazila_ids": [hierarchy.upazila_id]},
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 2  # PO + SK in upazila

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(PO_ID)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["assigned_module_ids"]) == 1

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(SK_ID)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["assigned_module_ids"]) == 1

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(SK_OTHER_ID)},
        )
        assert resp.status_code == 200
        assert resp.json()["assigned_module_ids"] == []

    async def test_create_assignment_validation(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module_1 = await _seed_module(db_session, "Validation Module")

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module_1.id), "user_ids": [AM_ID]},
        )
        assert resp.status_code == 400
        assert "Area Manager" in resp.json()["detail"]

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module_1.id)},
        )
        assert resp.status_code == 400
        assert (
            "user_ids, upazila_ids, district_ids, or division_ids must be provided" in resp.json()["detail"]
        )

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module_1.id), "user_ids": [999999]},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    async def test_create_assignment_user_ids_and_upazila_ids(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        hierarchy = await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module_1 = await _seed_module(db_session, "Combined Module")

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={
                "module_id": str(module_1.id),
                "user_ids": [SK_OTHER_ID],
                "upazila_ids": [hierarchy.upazila_id],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 3  # SK_OTHER + PO + SK in upazila

    async def test_create_assignment_by_district_ids(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        hierarchy = await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "District Module")

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "district_ids": [hierarchy.district_id]},
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 5

        list_resp = await client.get(platform_path(f"/admin/assignments/{module.id}/users"))
        assert list_resp.status_code == 200
        assert {user["id"] for user in list_resp.json()["users"]} == {
            AM_ID,
            PO_ID,
            PO_OTHER_ID,
            SK_ID,
            SK_OTHER_ID,
        }

    async def test_create_assignment_by_division_ids(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        hierarchy = await seed_multi_district_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Division Module")

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "division_ids": [hierarchy.division_id]},
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 7

    async def test_create_assignment_invalid_geography_ids(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Invalid Geography Module")

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "district_ids": [999999]},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "division_ids": [999999]},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

        resp = await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "upazila_ids": [999999]},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    async def test_sync_filtering_by_district_assignment(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        hierarchy = await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "District Assigned Module")

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "district_ids": [hierarchy.district_id]},
        )

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(AM_ID)},
        )
        assert resp.status_code == 200
        assert len(resp.json()["assigned_module_ids"]) == 1
        assert resp.json()["assigned_module_ids"][0]["module_id"] == str(module.id)


class TestAdminDocumentAssignments:
    async def test_create_document_assignment_po_only_by_default(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session)

        resp = await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id), "user_ids": [PO_ID]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["assigned_count"] == 1
        assert len(data["assignment_ids"]) == 1

    async def test_create_document_assignment_expands_po(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session)

        resp = await client.post(
            platform_path("/admin/document-assignments"),
            json={
                "source_document_id": str(doc.id),
                "user_ids": [PO_ID],
                "expand_po_assignees": True,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["assigned_count"] == 2
        assert len(data["assignment_ids"]) == 2

    async def test_create_document_assignment_by_upazila(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        hierarchy = await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session)

        resp = await client.post(
            platform_path("/admin/document-assignments"),
            json={
                "source_document_id": str(doc.id),
                "upazila_ids": [hierarchy.upazila_id],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 2

    async def test_create_document_assignment_idempotent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session)

        resp = await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id), "user_ids": [SK_ID]},
        )
        assert resp.status_code == 201
        first_ids = resp.json()["assignment_ids"]

        resp = await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id), "user_ids": [SK_ID]},
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 1
        assert resp.json()["assignment_ids"] == first_ids

    async def test_create_document_assignment_any_source_type(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = SourceDocument(
            title="Training Video",
            source_type="video",
            primary_language="bn",
            content_domain="clinical",
            original_storage_path=f"medtronics-storage/videos/{uuid4().hex}.mp4",
            original_filename="clip.mp4",
            tenant_id=1,
        )
        db_session.add(doc)
        await db_session.flush()
        await db_session.commit()

        resp = await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id), "user_ids": [SK_ID]},
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 1

    async def test_create_document_assignment_validation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session)

        resp = await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id), "user_ids": [AM_ID]},
        )
        assert resp.status_code == 400
        assert "Area Manager" in resp.json()["detail"]

        resp = await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id)},
        )
        assert resp.status_code == 400
        assert (
            "user_ids, upazila_ids, district_ids, or division_ids must be provided" in resp.json()["detail"]
        )

    async def test_create_document_assignment_by_district_ids(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        hierarchy = await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session)

        resp = await client.post(
            platform_path("/admin/document-assignments"),
            json={
                "source_document_id": str(doc.id),
                "district_ids": [hierarchy.district_id],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_count"] == 5

        list_resp = await client.get(platform_path(f"/admin/document-assignments/{doc.id}/users"))
        assert {user["id"] for user in list_resp.json()["users"]} == {
            AM_ID,
            PO_ID,
            PO_OTHER_ID,
            SK_ID,
            SK_OTHER_ID,
        }

    async def test_create_document_assignment_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()

        resp = await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(uuid4()), "user_ids": [SK_ID]},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "source_document_not_found"


class TestAdminModuleAssignmentUsers:
    async def test_list_module_assigned_users_after_po_assign(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Assigned Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "user_ids": [PO_ID]},
        )

        resp = await client.get(platform_path(f"/admin/assignments/{module.id}/users"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["module_id"] == str(module.id)
        assert len(data["users"]) == 1
        by_id = {user["id"]: user for user in data["users"]}
        assert by_id[PO_ID]["name"] == "Test PO"
        assert by_id[PO_ID]["role"] == "PO"

    async def test_list_module_assigned_users_after_po_expand(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Expanded Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={
                "module_id": str(module.id),
                "user_ids": [PO_ID],
                "expand_po_assignees": True,
            },
        )

        resp = await client.get(platform_path(f"/admin/assignments/{module.id}/users"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["module_id"] == str(module.id)
        assert len(data["users"]) == 2
        by_id = {user["id"]: user for user in data["users"]}
        assert by_id[PO_ID]["name"] == "Test PO"
        assert by_id[PO_ID]["role"] == "PO"
        assert by_id[SK_ID]["name"] == "Test Shastiya Kormi"
        assert by_id[SK_ID]["role"] == "SHASTIYA_KORMI"

    async def test_list_module_assigned_users_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Unassigned Module", tenant_id=0)

        resp = await client.get(platform_path(f"/admin/assignments/{module.id}/users"))
        assert resp.status_code == 200
        assert resp.json() == {"module_id": str(module.id), "users": []}

    async def test_list_module_assigned_users_not_found(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path(f"/admin/assignments/{uuid4()}/users"))
        assert resp.status_code == 404
        assert resp.json()["code"] == "module_not_found"


class TestAdminDocumentAssignmentUsers:
    async def test_list_document_assigned_users_after_po_assign(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session, tenant_id=0)

        await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id), "user_ids": [PO_ID]},
        )

        resp = await client.get(platform_path(f"/admin/document-assignments/{doc.id}/users"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_document_id"] == str(doc.id)
        assert len(data["users"]) == 1
        by_id = {user["id"]: user for user in data["users"]}
        assert by_id[PO_ID]["name"] == "Test PO"

    async def test_list_document_assigned_users_after_po_expand(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session, tenant_id=0)

        await client.post(
            platform_path("/admin/document-assignments"),
            json={
                "source_document_id": str(doc.id),
                "user_ids": [PO_ID],
                "expand_po_assignees": True,
            },
        )

        resp = await client.get(platform_path(f"/admin/document-assignments/{doc.id}/users"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_document_id"] == str(doc.id)
        assert len(data["users"]) == 2
        by_id = {user["id"]: user for user in data["users"]}
        assert by_id[PO_ID]["name"] == "Test PO"
        assert by_id[SK_ID]["name"] == "Test Shastiya Kormi"

    async def test_list_document_assigned_users_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session, tenant_id=0)

        resp = await client.get(platform_path(f"/admin/document-assignments/{doc.id}/users"))
        assert resp.status_code == 200
        assert resp.json() == {"source_document_id": str(doc.id), "users": []}

    async def test_list_document_assigned_users_not_found(self, client: AsyncClient) -> None:
        resp = await client.get(platform_path(f"/admin/document-assignments/{uuid4()}/users"))
        assert resp.status_code == 404
        assert resp.json()["code"] == "source_document_not_found"


class TestAdminModuleAssignmentUpdate:
    async def test_update_module_assignments_replace_adds_and_removes(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Replace Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "user_ids": [SK_ID, SK_OTHER_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={"user_ids": [SK_OTHER_ID, PO_ID]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["added_count"] == 1
        assert data["removed_count"] == 1
        assert len(data["assignment_ids"]) == 2

        list_resp = await client.get(platform_path(f"/admin/assignments/{module.id}/users"))
        user_ids = {user["id"] for user in list_resp.json()["users"]}
        assert user_ids == {SK_OTHER_ID, PO_ID}

    async def test_update_module_assignments_replace_expands_po(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Replace Expand Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "user_ids": [SK_ID, SK_OTHER_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={"user_ids": [SK_OTHER_ID, PO_ID], "expand_po_assignees": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["added_count"] == 1
        assert data["removed_count"] == 0
        assert len(data["assignment_ids"]) == 3

        list_resp = await client.get(platform_path(f"/admin/assignments/{module.id}/users"))
        user_ids = {user["id"] for user in list_resp.json()["users"]}
        assert user_ids == {SK_OTHER_ID, PO_ID, SK_ID}

    async def test_update_module_assignments_idempotent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Idempotent Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "user_ids": [SK_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={"user_ids": [SK_ID]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["added_count"] == 0
        assert data["removed_count"] == 0
        assert len(data["assignment_ids"]) == 1

    async def test_update_module_assignments_clear_all(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Clear Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "user_ids": [SK_ID, SK_OTHER_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["added_count"] == 0
        assert data["removed_count"] == 2
        assert data["assignment_ids"] == []

        list_resp = await client.get(platform_path(f"/admin/assignments/{module.id}/users"))
        assert list_resp.json()["users"] == []

    async def test_update_module_assignments_po_only_by_default(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "PO Only Replace Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={
                "module_id": str(module.id),
                "user_ids": [PO_ID],
                "expand_po_assignees": True,
            },
        )

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={"user_ids": [PO_ID]},
        )
        assert resp.status_code == 200
        assert resp.json()["added_count"] == 0
        assert resp.json()["removed_count"] == 1

        list_resp = await client.get(platform_path(f"/admin/assignments/{module.id}/users"))
        user_ids = {user["id"] for user in list_resp.json()["users"]}
        assert user_ids == {PO_ID}

    async def test_update_module_assignments_po_expansion(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "PO Replace Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "user_ids": [SK_OTHER_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={"user_ids": [PO_ID], "expand_po_assignees": True},
        )
        assert resp.status_code == 200
        assert resp.json()["added_count"] == 2
        assert resp.json()["removed_count"] == 1

        list_resp = await client.get(platform_path(f"/admin/assignments/{module.id}/users"))
        user_ids = {user["id"] for user in list_resp.json()["users"]}
        assert user_ids == {PO_ID, SK_ID}

    async def test_update_module_assignments_by_division_ids(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        hierarchy = await seed_multi_district_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Division Replace Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "user_ids": [SK_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={"division_ids": [hierarchy.division_id]},
        )
        assert resp.status_code == 200
        assert resp.json()["added_count"] == 6
        assert resp.json()["removed_count"] == 0
        assert len(resp.json()["assignment_ids"]) == 7

        list_resp = await client.get(platform_path(f"/admin/assignments/{module.id}/users"))
        assert len(list_resp.json()["users"]) == 7

    async def test_update_module_assignments_validation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Validation Update Module", tenant_id=0)

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={"user_ids": [AM_ID]},
        )
        assert resp.status_code == 400
        assert "Area Manager" in resp.json()["detail"]

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={"user_ids": [999999]},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    async def test_update_module_assignments_not_found(self, client: AsyncClient) -> None:
        resp = await client.put(
            platform_path(f"/admin/assignments/{uuid4()}/users"),
            json={"user_ids": [SK_ID]},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "module_not_found"

    async def test_update_module_assignments_rejects_non_assignable_add(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        family = ModuleFamily(module_code=f"faq-{uuid4().hex[:8]}", tenant_id=0)
        db_session.add(family)
        await db_session.flush()
        module = Module(
            module_family_id=family.id,
            version=1,
            title_localized={"bn": "FAQ Only"},
            domain="rmnch",
            module_type="refresher",
            lifecycle_status="published",
            module_json={"cards": [{"title": {"bn": "c"}}]},
            published_at=datetime.now(UTC),
            chatbot_faqs_only=True,
            tenant_id=0,
        )
        db_session.add(module)
        await db_session.flush()
        family.current_published_module_id = module.id
        await db_session.commit()

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={"user_ids": [SK_ID]},
        )
        assert resp.status_code == 400
        assert "cannot be assigned" in resp.json()["detail"]

    async def test_update_module_assignments_allows_clear_on_non_assignable(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Clear Published Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "user_ids": [SK_ID]},
        )

        module.chatbot_faqs_only = True
        await db_session.commit()

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["removed_count"] == 1
        assert resp.json()["added_count"] == 0

    async def test_update_module_assignments_sync_side_effect(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        module = await _seed_module(db_session, "Sync Side Effect Module", tenant_id=0)

        await client.post(
            platform_path("/admin/assignments"),
            json={"module_id": str(module.id), "user_ids": [SK_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/assignments/{module.id}/users"),
            json={"user_ids": [SK_OTHER_ID]},
        )
        assert resp.status_code == 200

        resp = await client.get(
            platform_path("/sync/modules"),
            params={"since": "2020-01-01T00:00:00Z"},
            headers={"x-mock-user-id": str(SK_ID)},
        )
        assert resp.status_code == 200
        assert resp.json()["assigned_module_ids"] == []


class TestAdminDocumentAssignmentUpdate:
    async def test_update_document_assignments_replace_adds_and_removes(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session, tenant_id=0)

        await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id), "user_ids": [SK_ID, SK_OTHER_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/document-assignments/{doc.id}/users"),
            json={"user_ids": [SK_OTHER_ID, PO_ID]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["added_count"] == 1
        assert data["removed_count"] == 1
        assert len(data["assignment_ids"]) == 2

    async def test_update_document_assignments_idempotent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session, tenant_id=0)

        await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id), "user_ids": [SK_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/document-assignments/{doc.id}/users"),
            json={"user_ids": [SK_ID]},
        )
        assert resp.status_code == 200
        assert resp.json()["added_count"] == 0
        assert resp.json()["removed_count"] == 0
        assert len(resp.json()["assignment_ids"]) == 1

    async def test_update_document_assignments_clear_all(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session, tenant_id=0)

        await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id), "user_ids": [SK_ID, PO_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/document-assignments/{doc.id}/users"),
            json={"user_ids": [], "upazila_ids": [], "district_ids": [], "division_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["removed_count"] == 2
        assert resp.json()["assignment_ids"] == []

        list_resp = await client.get(platform_path(f"/admin/document-assignments/{doc.id}/users"))
        assert list_resp.json()["users"] == []

    async def test_update_document_assignments_po_expansion(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session, tenant_id=0)

        await client.post(
            platform_path("/admin/document-assignments"),
            json={"source_document_id": str(doc.id), "user_ids": [SK_OTHER_ID]},
        )

        resp = await client.put(
            platform_path(f"/admin/document-assignments/{doc.id}/users"),
            json={"user_ids": [PO_ID], "expand_po_assignees": True},
        )
        assert resp.status_code == 200
        assert resp.json()["added_count"] == 2
        assert resp.json()["removed_count"] == 1

    async def test_update_document_assignments_validation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()
        doc = await _seed_source_document(db_session, tenant_id=0)

        resp = await client.put(
            platform_path(f"/admin/document-assignments/{doc.id}/users"),
            json={"user_ids": [AM_ID]},
        )
        assert resp.status_code == 400
        assert "Area Manager" in resp.json()["detail"]

    async def test_update_document_assignments_not_found(self, client: AsyncClient) -> None:
        resp = await client.put(
            platform_path(f"/admin/document-assignments/{uuid4()}/users"),
            json={"user_ids": [SK_ID]},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "source_document_not_found"
