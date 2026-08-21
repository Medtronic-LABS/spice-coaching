"""Admin hierarchy CSV/XLSX import API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from io import BytesIO

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import register_problem_handlers
from openpyxl import Workbook
from platform_service.api.hierarchy import router as hierarchy_router
from platform_service.auth.spice_context import SpiceUserContext
from platform_service.config import get_settings
from platform_service.db.models.hierarchy_user import ROLE_SUPER_ADMIN, HierarchyUser
from platform_service.db.models.role import Role
from platform_service.deps import get_db
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import platform_path, requires_db
from tests.helpers.hierarchy_fixtures import ensure_hierarchy_roles, hierarchy_user, seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]

_SAMPLE_HEADER = (
    "Division,District,Upazila,AM name,AM mHealth Account,Rural PO Name,PO User_Id,Sk Name,SK user_id\n"
)

_SAMPLE_ROWS = (
    "Rangpur,Lalmonirhat,Lalmonirhat Sadar,Mudassar Raza,422,Ismael Kureshi,424,Zulfikur Rehman,427\n"
    "Rangpur,Lalmonirhat,Lalmonirhat Sadar,Mudassar Raza,422,Saba Begum,425,Shahbaz Kurmi,428\n"
    "Rangpur,Lalmonirhat,Patgram,Shazeb Ata,423,Nishad Alam,426,Zeeshan Haider,429\n"
)


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data_between_tests(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text('TRUNCATE "users", district, upazila, user_upazila, division RESTART IDENTITY CASCADE')
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    app_obj = FastAPI()
    register_problem_handlers(
        app_obj,
        validation_error_type=RequestValidationError,
        http_exception_type=HTTPException,
    )
    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(hierarchy_router)
    app_obj.include_router(api_router)

    @app_obj.middleware("http")
    async def inject_spice_user(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.spice_user = SpiceUserContext.model_validate(
            {"id": 1, "username": "admin", "isSuperUser": True, "roles": []}
        )
        request.state.selected_tenant_id = 0
        return await call_next(request)

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


def _csv_bytes(body: str) -> bytes:
    return body.encode("utf-8")


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buf = BytesIO()
    workbook.save(buf)
    return buf.getvalue()


class TestAdminHierarchyImport:
    async def test_csv_import_creates_geo_and_users(self, client: AsyncClient) -> None:
        response = await client.post(
            platform_path("/admin/hierarchy/import"),
            files={"file": ("hierarchy.csv", _csv_bytes(_SAMPLE_HEADER + _SAMPLE_ROWS), "text/csv")},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["divisions"]["created"] == 1
        assert body["districts"]["created"] == 1
        assert body["upazilas"]["created"] == 2
        assert body["users"]["created"] == 8

        users = (await client.get(platform_path("/admin/hierarchy/users"), params={"limit": 200})).json()
        assert users["total"] == 8
        by_id = {u["id"]: u for u in users["users"]}
        assert by_id[422]["role"] == "AREA_MANAGER"
        assert by_id[422]["name"] == "Mudassar Raza"
        assert {u["name"] for u in by_id[422]["upazilas"]} == {"Lalmonirhat Sadar"}
        assert by_id[424]["parent_id"] == 422
        assert by_id[427]["parent_id"] == 424
        assert by_id[423]["role"] == "AREA_MANAGER"
        assert {u["name"] for u in by_id[423]["upazilas"]} == {"Patgram"}

    async def test_second_import_updates_and_deletes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        await seed_basic_hierarchy(db_session)
        await db_session.commit()

        csv_body = (
            _SAMPLE_HEADER
            + "Rangpur,Lalmonirhat,Lalmonirhat Sadar,AM Renamed,1001,PO Renamed,2001,SK Renamed,3001\n"
        )
        response = await client.post(
            platform_path("/admin/hierarchy/import"),
            files={"file": ("hierarchy.csv", _csv_bytes(csv_body), "text/csv")},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["users"]["updated"] >= 1
        assert body["users"]["deleted"] >= 1

        users = (await client.get(platform_path("/admin/hierarchy/users"), params={"limit": 200})).json()
        ids = {u["id"] for u in users["users"]}
        assert ids == {1001, 2001, 3001}
        by_id = {u["id"]: u for u in users["users"]}
        assert by_id[1001]["name"] == "AM Renamed"
        assert by_id[2001]["name"] == "PO Renamed"
        assert by_id[3001]["name"] == "SK Renamed"

    async def test_xlsx_import_smoke(self, client: AsyncClient) -> None:
        rows = [
            [
                "Division",
                "District",
                "Upazila",
                "AM name",
                "AM mHealth Account",
                "Rural PO Name",
                "PO User_Id",
                "Sk Name",
                "SK user_id",
            ],
            [
                "Rangpur",
                "Lalmonirhat",
                "Lalmonirhat Sadar",
                "Mudassar Raza",
                422,
                "Ismael Kureshi",
                424,
                "Zulfikur Rehman",
                427,
            ],
        ]
        response = await client.post(
            platform_path("/admin/hierarchy/import"),
            files={
                "file": (
                    "hierarchy.xlsx",
                    _xlsx_bytes(rows),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["users"]["created"] == 3

    async def test_conflict_same_id_two_districts_rejects(self, client: AsyncClient) -> None:
        csv_body = (
            _SAMPLE_HEADER + "Rangpur,Lalmonirhat,Lalmonirhat Sadar,Mudassar Raza,422,Ismael Kureshi,424,"
            "Zulfikur Rehman,427\n" + "Dhaka,Dhaka,Savar,Mudassar Raza,422,Other PO,500,Other SK,501\n"
        )
        response = await client.post(
            platform_path("/admin/hierarchy/import"),
            files={"file": ("bad.csv", _csv_bytes(csv_body), "text/csv")},
        )
        assert response.status_code == 400
        assert response.json()["code"] == ErrorCode.HIERARCHY_IMPORT_INVALID.value

        users = (await client.get(platform_path("/admin/hierarchy/users"))).json()
        assert users["total"] == 0
        divisions = (await client.get(platform_path("/admin/divisions"))).json()
        assert divisions["total"] == 0

    async def test_bad_headers_reject(self, client: AsyncClient) -> None:
        response = await client.post(
            platform_path("/admin/hierarchy/import"),
            files={"file": ("bad.csv", b"foo,bar\n1,2\n", "text/csv")},
        )
        assert response.status_code == 400
        assert response.json()["code"] == ErrorCode.HIERARCHY_IMPORT_INVALID.value

    async def test_empty_file_reject(self, client: AsyncClient) -> None:
        response = await client.post(
            platform_path("/admin/hierarchy/import"),
            files={"file": ("empty.csv", b"", "text/csv")},
        )
        assert response.status_code == 400
        assert response.json()["code"] == ErrorCode.HIERARCHY_IMPORT_INVALID.value

    async def test_super_admin_preserved(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        seed = await seed_basic_hierarchy(db_session)
        roles = await ensure_hierarchy_roles(db_session)
        if ROLE_SUPER_ADMIN not in roles:
            row = Role(code=ROLE_SUPER_ADMIN)
            db_session.add(row)
            await db_session.flush()
            roles[ROLE_SUPER_ADMIN] = row

        admin = await hierarchy_user(
            db_session,
            user_id=9001,
            name="Platform Admin",
            role=ROLE_SUPER_ADMIN,
            district_id=seed.district_id,
            tenant_id=seed.tenant_id,
            parent_id=None,
        )
        admin.role_row = roles[ROLE_SUPER_ADMIN]
        admin.role_id = roles[ROLE_SUPER_ADMIN].id
        db_session.add(admin)
        await db_session.commit()

        csv_body = (
            _SAMPLE_HEADER
            + "Rangpur,Lalmonirhat,Lalmonirhat Sadar,AM Renamed,1001,PO Renamed,2001,SK Renamed,3001\n"
        )
        response = await client.post(
            platform_path("/admin/hierarchy/import"),
            files={"file": ("hierarchy.csv", _csv_bytes(csv_body), "text/csv")},
        )
        assert response.status_code == 200, response.text

        remaining = (
            await db_session.execute(select(HierarchyUser).where(HierarchyUser.id == 9001))
        ).scalar_one_or_none()
        assert remaining is not None
        assert remaining.name == "Platform Admin"
