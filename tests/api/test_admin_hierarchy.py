"""Admin hierarchy API integration tests (districts + upazilas + users)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import register_problem_handlers
from platform_service.api.hierarchy import router as hierarchy_router
from platform_service.config import get_settings
from platform_service.deps import get_db
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
)

pytestmark = [requires_db, pytest.mark.asyncio]


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


class TestAdminHierarchy:
    async def test_district_upazila_and_user_crud_chain(self, client: AsyncClient) -> None:
        create_district = await client.post(
            platform_path("/admin/districts"),
            json={"name": "Dhaka"},
        )
        assert create_district.status_code == 201
        district = create_district.json()
        district_id = district["id"]
        assert district["name"] == "Dhaka"
        assert district["tenant_id"] == 0

        # Create two upazilas in Dhaka
        u1 = (
            await client.post(
                platform_path("/admin/upazilas"),
                json={"name": "Savar", "district_id": district_id},
            )
        ).json()
        u2 = (
            await client.post(
                platform_path("/admin/upazilas"),
                json={"name": "Dhamrai", "district_id": district_id},
            )
        ).json()
        upazila_1_id = u1["id"]
        upazila_2_id = u2["id"]

        list_upazilas = await client.get(
            platform_path("/admin/upazilas"), params={"district_id": district_id}
        )
        assert list_upazilas.status_code == 200
        assert list_upazilas.json()["total"] == 2

        # Create AM assigned to both upazilas
        am = await client.post(
            platform_path("/admin/hierarchy/users"),
            json={
                "id": 1001,
                "name": "AM One",
                "role": "AREA_MANAGER",
                "parent_id": None,
                "district_id": district_id,
                "upazila_ids": [upazila_1_id, upazila_2_id],
            },
        )
        assert am.status_code == 201
        assert am.json()["id"] == 1001
        assert len(am.json()["upazilas"]) == 2

        # Create PM assigned to upazila_1 (subset of AM)
        pm = await client.post(
            platform_path("/admin/hierarchy/users"),
            json={
                "id": 2001,
                "name": "PM One",
                "role": "PO",
                "parent_id": 1001,
                "district_id": district_id,
                "upazila_ids": [upazila_1_id],
            },
        )
        assert pm.status_code == 201
        assert len(pm.json()["upazilas"]) == 1

        # Create SK assigned to upazila_1 (subset of PM)
        sk = await client.post(
            platform_path("/admin/hierarchy/users"),
            json={
                "id": 3001,
                "name": "SK One",
                "role": "SHASTIYA_KORMI",
                "parent_id": 2001,
                "district_id": district_id,
                "upazila_ids": [upazila_1_id],
            },
        )
        assert sk.status_code == 201

        # Update SK to assign upazila_2 (which PM does NOT have) -> Should be rejected
        bad_sk_update = await client.put(
            platform_path("/admin/hierarchy/users/3001"),
            json={
                "name": "SK Updated",
                "role": "SHASTIYA_KORMI",
                "parent_id": 2001,
                "district_id": district_id,
                "upazila_ids": [upazila_2_id],
            },
        )
        assert bad_sk_update.status_code == 400
        assert bad_sk_update.json()["code"] == ErrorCode.HIERARCHY_UPAZILA_INVALID.value

        delete_pm = await client.delete(platform_path("/admin/hierarchy/users/2001"))
        assert delete_pm.status_code == 204

        missing_sk = await client.get(platform_path("/admin/hierarchy/users/3001"))
        assert missing_sk.status_code == 404
        assert missing_sk.json()["code"] == ErrorCode.HIERARCHY_USER_NOT_FOUND.value

    async def test_invalid_parent_role_rejected(self, client: AsyncClient) -> None:
        district = (await client.post(platform_path("/admin/districts"), json={"name": "Rajshahi"})).json()
        district_id = district["id"]
        u1 = (
            await client.post(
                platform_path("/admin/upazilas"),
                json={"name": "Boalia", "district_id": district_id},
            )
        ).json()

        await client.post(
            platform_path("/admin/hierarchy/users"),
            json={
                "id": 4001,
                "name": "AM",
                "role": "AREA_MANAGER",
                "parent_id": None,
                "district_id": district_id,
                "upazila_ids": [u1["id"]],
            },
        )
        bad = await client.post(
            platform_path("/admin/hierarchy/users"),
            json={
                "id": 4002,
                "name": "SK without PM",
                "role": "SHASTIYA_KORMI",
                "parent_id": 4001,
                "district_id": district_id,
                "upazila_ids": [u1["id"]],
            },
        )
        assert bad.status_code == 400
        assert bad.json()["code"] == ErrorCode.HIERARCHY_PARENT_INVALID.value

    async def test_duplicate_user_id_conflict(self, client: AsyncClient) -> None:
        district = (await client.post(platform_path("/admin/districts"), json={"name": "Khulna"})).json()
        u1 = (
            await client.post(
                platform_path("/admin/upazilas"),
                json={"name": "Khalishpur", "district_id": district["id"]},
            )
        ).json()
        payload = {
            "id": 5001,
            "name": "AM",
            "role": "AREA_MANAGER",
            "parent_id": None,
            "district_id": district["id"],
            "upazila_ids": [u1["id"]],
        }
        first = await client.post(platform_path("/admin/hierarchy/users"), json=payload)
        assert first.status_code == 201
        second = await client.post(platform_path("/admin/hierarchy/users"), json=payload)
        assert second.status_code == 409
        assert second.json()["code"] == ErrorCode.HIERARCHY_USER_CONFLICT.value

    async def test_list_all_users_pages_past_limit(self, db_session: AsyncSession) -> None:
        from platform_service.db.models.hierarchy_user import HierarchyUser
        from platform_service.services.hierarchy_service import HierarchyService

        await seed_basic_hierarchy(db_session, tenant_id=0)
        district_id = (await db_session.execute(text("SELECT id FROM district LIMIT 1"))).scalar_one()
        for i in range(5):
            db_session.add(
                HierarchyUser(
                    id=3100 + i,
                    name=f"Extra SK {i}",
                    role="SHASTIYA_KORMI",
                    parent_id=PO_ID,
                    district_id=district_id,
                    tenant_id=0,
                    created_by="test",
                    updated_by="test",
                )
            )
        await db_session.commit()

        users = await HierarchyService(db_session).list_all_users(tenant_id=0, page_size=2)
        assert len(users) >= 7
        assert len({u.id for u in users}) == len(users)

    async def test_list_users_filters_by_upazila_id(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=0)
        await db_session.commit()

        resp = await client.get(
            platform_path("/admin/hierarchy/users"),
            params={"upazila_id": seed.upazila_id},
        )
        assert resp.status_code == 200
        body = resp.json()
        user_ids = {u["id"] for u in body["users"]}
        assert user_ids == {PO_ID, SK_ID}
        assert body["total"] == 2
        assert AM_ID not in user_ids
        assert PO_OTHER_ID not in user_ids
        assert SK_OTHER_ID not in user_ids

    async def test_list_users_upazila_id_ands_with_role(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=0)
        await db_session.commit()

        resp = await client.get(
            platform_path("/admin/hierarchy/users"),
            params={"upazila_id": seed.upazila_id, "role": "PO"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert {u["id"] for u in body["users"]} == {PO_ID}
        assert body["total"] == 1

    async def test_list_users_upazila_id_ands_with_district(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=0)
        await db_session.commit()

        match = await client.get(
            platform_path("/admin/hierarchy/users"),
            params={"upazila_id": seed.upazila_id, "district_id": seed.district_id},
        )
        assert match.status_code == 200
        assert {u["id"] for u in match.json()["users"]} == {PO_ID, SK_ID}

        conflict = await client.get(
            platform_path("/admin/hierarchy/users"),
            params={"upazila_id": seed.upazila_id, "district_id": seed.district_id + 999},
        )
        assert conflict.status_code == 200
        assert conflict.json()["users"] == []
        assert conflict.json()["total"] == 0

    async def test_list_users_unknown_upazila_id_returns_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session, tenant_id=0)
        await db_session.commit()

        resp = await client.get(
            platform_path("/admin/hierarchy/users"),
            params={"upazila_id": 999_999},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["users"] == []
        assert body["total"] == 0


class TestHierarchyNameQuery:
    async def test_list_districts_q_filters_by_name(self, client: AsyncClient) -> None:
        await client.post(platform_path("/admin/districts"), json={"name": "Dhaka"})
        await client.post(platform_path("/admin/districts"), json={"name": "Rajshahi"})

        resp = await client.get(platform_path("/admin/districts"), params={"q": "dhak"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert [d["name"] for d in body["districts"]] == ["Dhaka"]

        case = await client.get(platform_path("/admin/districts"), params={"q": "RAJ"})
        assert case.status_code == 200
        assert [d["name"] for d in case.json()["districts"]] == ["Rajshahi"]
        assert case.json()["total"] == 1

    async def test_list_districts_empty_q_returns_all(self, client: AsyncClient) -> None:
        await client.post(platform_path("/admin/districts"), json={"name": "Dhaka"})
        await client.post(platform_path("/admin/districts"), json={"name": "Rajshahi"})

        omitted = await client.get(platform_path("/admin/districts"))
        whitespace = await client.get(platform_path("/admin/districts"), params={"q": "   "})
        assert omitted.status_code == 200
        assert whitespace.status_code == 200
        assert omitted.json()["total"] == 2
        assert whitespace.json()["total"] == 2

    async def test_list_upazilas_q_filters_by_name(self, client: AsyncClient) -> None:
        district = (await client.post(platform_path("/admin/districts"), json={"name": "Dhaka"})).json()
        district_id = district["id"]
        await client.post(
            platform_path("/admin/upazilas"),
            json={"name": "Savar", "district_id": district_id},
        )
        await client.post(
            platform_path("/admin/upazilas"),
            json={"name": "Dhamrai", "district_id": district_id},
        )

        resp = await client.get(platform_path("/admin/upazilas"), params={"q": "sav"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert [u["name"] for u in body["upazilas"]] == ["Savar"]

        case = await client.get(platform_path("/admin/upazilas"), params={"q": "DHAM"})
        assert case.status_code == 200
        assert [u["name"] for u in case.json()["upazilas"]] == ["Dhamrai"]
        assert case.json()["total"] == 1

    async def test_list_upazilas_q_ands_with_district_id(self, client: AsyncClient) -> None:
        d1 = (await client.post(platform_path("/admin/districts"), json={"name": "Dhaka"})).json()
        d2 = (await client.post(platform_path("/admin/districts"), json={"name": "Rajshahi"})).json()
        await client.post(
            platform_path("/admin/upazilas"),
            json={"name": "Savar", "district_id": d1["id"]},
        )
        await client.post(
            platform_path("/admin/upazilas"),
            json={"name": "Savar North", "district_id": d2["id"]},
        )

        resp = await client.get(
            platform_path("/admin/upazilas"),
            params={"q": "savar", "district_id": d1["id"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["upazilas"][0]["name"] == "Savar"
        assert body["upazilas"][0]["district_id"] == d1["id"]

        omitted_q = await client.get(platform_path("/admin/upazilas"), params={"q": "   "})
        assert omitted_q.status_code == 200
        assert omitted_q.json()["total"] == 2

    async def test_list_users_q_filters_by_name(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session, tenant_id=0)
        await db_session.commit()

        resp = await client.get(platform_path("/admin/hierarchy/users"), params={"q": "area"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["users"][0]["id"] == AM_ID
        assert body["users"][0]["name"] == "Test Area Manager"

        case = await client.get(platform_path("/admin/hierarchy/users"), params={"q": "OTHER"})
        assert case.status_code == 200
        ids = {u["id"] for u in case.json()["users"]}
        assert ids == {PO_OTHER_ID, SK_OTHER_ID}
        assert case.json()["total"] == 2

    async def test_list_users_empty_q_returns_all(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session, tenant_id=0)
        await db_session.commit()

        omitted = await client.get(platform_path("/admin/hierarchy/users"))
        whitespace = await client.get(
            platform_path("/admin/hierarchy/users"),
            params={"q": "   "},
        )
        assert omitted.status_code == 200
        assert whitespace.status_code == 200
        assert omitted.json()["total"] == 5
        assert whitespace.json()["total"] == 5

    async def test_list_users_q_ands_with_district_and_role(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=0)
        await db_session.commit()

        resp = await client.get(
            platform_path("/admin/hierarchy/users"),
            params={"q": "po", "district_id": seed.district_id, "role": "PO"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert {u["id"] for u in body["users"]} == {PO_ID, PO_OTHER_ID}
        assert body["total"] == 2

        role_narrow = await client.get(
            platform_path("/admin/hierarchy/users"),
            params={"q": "other", "role": "SHASTIYA_KORMI"},
        )
        assert role_narrow.status_code == 200
        assert {u["id"] for u in role_narrow.json()["users"]} == {SK_OTHER_ID}
        assert role_narrow.json()["total"] == 1


class TestAdminDivisions:
    async def test_division_district_and_user_chain(self, client: AsyncClient) -> None:
        create_division = await client.post(
            platform_path("/admin/divisions"),
            json={"name": "Dhaka Division"},
        )
        assert create_division.status_code == 201
        division = create_division.json()
        division_id = division["id"]
        assert division["name"] == "Dhaka Division"

        create_district = await client.post(
            platform_path("/admin/districts"),
            json={"name": "Dhaka", "division_id": division_id},
        )
        assert create_district.status_code == 201
        district = create_district.json()
        assert district["division_id"] == division_id
        assert district["division"] == "Dhaka Division"

        update_district = await client.put(
            platform_path(f"/admin/districts/{district['id']}"),
            json={"name": "Dhaka Metro", "division_id": division_id},
        )
        assert update_district.status_code == 200
        assert update_district.json()["name"] == "Dhaka Metro"

        list_districts = await client.get(
            platform_path("/admin/districts"),
            params={"division_id": division_id},
        )
        assert list_districts.status_code == 200
        assert list_districts.json()["total"] == 1

        missing_division = await client.post(
            platform_path("/admin/districts"),
            json={"name": "No Division", "division_id": division_id + 999},
        )
        assert missing_division.status_code == 404
        assert missing_division.json()["code"] == ErrorCode.HIERARCHY_DIVISION_NOT_FOUND.value

    async def test_list_users_filters_by_division_id(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        seed = await seed_basic_hierarchy(db_session, tenant_id=0)
        await db_session.commit()

        resp = await client.get(
            platform_path("/admin/hierarchy/users"),
            params={"division_id": seed.division_id},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 5
        assert all(u["division_id"] == seed.division_id for u in resp.json()["users"])

        empty = await client.get(
            platform_path("/admin/hierarchy/users"),
            params={"division_id": seed.division_id + 999},
        )
        assert empty.status_code == 200
        assert empty.json()["total"] == 0

    async def test_delete_division_cascades_districts(self, client: AsyncClient) -> None:
        division = (
            await client.post(platform_path("/admin/divisions"), json={"name": "Khulna Division"})
        ).json()
        district = (
            await client.post(
                platform_path("/admin/districts"),
                json={"name": "Khulna", "division_id": division["id"]},
            )
        ).json()

        delete = await client.delete(platform_path(f"/admin/divisions/{division['id']}"))
        assert delete.status_code == 204

        missing_district = await client.get(platform_path(f"/admin/districts/{district['id']}"))
        assert missing_district.status_code == 404
