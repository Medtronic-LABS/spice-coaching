"""Admin badges API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_foundation.problem import register_problem_handlers
from platform_service.api.badges import router as badges_router
from platform_service.auth.spice_context import SpiceUserContext
from platform_service.config import get_settings
from platform_service.db.models.badge import Badge
from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily
from platform_service.deps import get_db
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import platform_path, requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data_between_tests(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text("TRUNCATE badge_module, badge, module, module_family RESTART IDENTITY CASCADE")
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
    api_router.include_router(badges_router)
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


async def _seed_module(
    session: AsyncSession,
    *,
    title: str = "Sample",
    domain: str = "rmnch",
    lifecycle_status: str = "published",
) -> Module:
    family = ModuleFamily(module_code=f"f-{uuid4().hex[:8]}", tenant_id=1)
    session.add(family)
    await session.flush()
    module = Module(
        module_family_id=family.id,
        version=1,
        title_localized={"bn": title, "en": title},
        domain=domain,
        module_type="refresher",
        lifecycle_status=lifecycle_status,
        module_json={"cards": [{"title": {"bn": "c"}}]},
        published_at=datetime.now(UTC) if lifecycle_status == "published" else None,
        tenant_id=1,
    )
    session.add(module)
    await session.flush()
    if lifecycle_status == "published":
        family.current_published_module_id = module.id
        await session.flush()
    await session.commit()
    return module


class TestAdminBadges:
    async def test_crud_workflow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        module_1 = await _seed_module(db_session, title="M1", domain="rmnch")
        module_2 = await _seed_module(db_session, title="M2", domain="clinical")

        create = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "First Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/first.png",
                "module_ids": [str(module_1.id), str(module_2.id)],
            },
        )
        assert create.status_code == 201
        created = create.json()
        badge_id = created["id"]
        assert created["name"] == "First Badge"
        assert created["domain"] == "rmnch"
        assert created["image_storage_path"] == "badges/first.png"
        assert created["status"] == "active"
        assert created["sequence"] is None
        assert set(created["module_ids"]) == {str(module_1.id), str(module_2.id)}
        created_modules = {item["id"]: item for item in created["modules"]}
        assert set(created_modules) == {str(module_1.id), str(module_2.id)}
        assert created_modules[str(module_1.id)]["title"] == {"bn": "M1", "en": "M1"}
        assert created_modules[str(module_2.id)]["title"] == {"bn": "M2", "en": "M2"}
        assert created["created_by"] is None
        assert created["updated_by"] is None

        get_resp = await client.get(platform_path(f"/admin/badges/{badge_id}"))
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == badge_id
        assert get_resp.json()["created_by"] is None
        assert get_resp.json()["updated_by"] is None
        assert len(get_resp.json()["modules"]) == 2

        update = await client.put(
            platform_path(f"/admin/badges/{badge_id}"),
            json={
                "name": "Updated Badge",
                "domain": "clinical",
                "image_storage_path": "badges/updated.png",
                "module_ids": [str(module_2.id)],
            },
        )
        assert update.status_code == 200
        updated = update.json()
        assert updated["name"] == "Updated Badge"
        assert updated["domain"] == "clinical"
        assert updated["module_ids"] == [str(module_2.id)]
        assert updated["modules"] == [
            {"id": str(module_2.id), "title": {"bn": "M2", "en": "M2"}},
        ]
        assert updated["created_by"] is None
        assert updated["updated_by"] is None

        delete = await client.delete(platform_path(f"/admin/badges/{badge_id}"))
        assert delete.status_code == 204

        get_deleted = await client.get(platform_path(f"/admin/badges/{badge_id}"))
        assert get_deleted.status_code == 404
        assert get_deleted.json()["code"] == "badge_not_found"

        list_resp = await client.get(platform_path("/admin/badges"))
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 0
        assert list_resp.json()["badges"] == []

    async def test_list_filters_and_pagination(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(db_session, domain="rmnch")
        await _seed_module(db_session, domain="clinical")

        await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Alpha Care",
                "domain": "rmnch",
                "image_storage_path": "badges/a.png",
                "module_ids": [],
            },
        )
        await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Beta Care",
                "domain": "clinical",
                "image_storage_path": "badges/b.png",
                "module_ids": [],
            },
        )
        await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Alpha Ops",
                "domain": "rmnch",
                "image_storage_path": "badges/c.png",
                "module_ids": [],
            },
        )

        by_domain = await client.get(platform_path("/admin/badges"), params={"domain": "rmnch"})
        assert by_domain.status_code == 200
        assert by_domain.json()["total"] == 2
        assert all(b["domain"] == "rmnch" for b in by_domain.json()["badges"])

        by_name = await client.get(platform_path("/admin/badges"), params={"q": "alpha"})
        assert by_name.status_code == 200
        assert by_name.json()["total"] == 2
        assert all("Alpha" in b["name"] for b in by_name.json()["badges"])

        page = await client.get(
            platform_path("/admin/badges"),
            params={"limit": 1, "offset": 0},
        )
        assert page.status_code == 200
        assert page.json()["total"] == 3
        assert page.json()["total_pages"] == 3
        assert len(page.json()["badges"]) == 1

    async def test_list_created_by_filter(
        self,
        client_with_spice: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        await _seed_module(db_session, domain="rmnch")

        for username, name in (
            ("alice", "Alice Badge"),
            ("bob", "Bob Badge"),
            ("carol", "Carol Badge"),
        ):
            resp = await client_with_spice.post(
                platform_path("/admin/badges"),
                json={
                    "name": name,
                    "domain": "rmnch",
                    "image_storage_path": f"badges/{username}.png",
                    "module_ids": [],
                },
                headers={"X-Test-Username": username},
            )
            assert resp.status_code == 201

        # NULL creator (no spice on plain create path is separate; set one row null).
        null_creator = (
            await db_session.execute(select(Badge).where(Badge.name == "Carol Badge"))
        ).scalar_one()
        null_creator.created_by = None
        await db_session.commit()

        by_alice = await client_with_spice.get(
            platform_path("/admin/badges"),
            params={"created_by": "alice"},
        )
        assert by_alice.status_code == 200
        assert by_alice.json()["total"] == 1
        assert by_alice.json()["badges"][0]["name"] == "Alice Badge"
        assert by_alice.json()["badges"][0]["created_by"] == "alice"

        by_multi = await client_with_spice.get(
            platform_path("/admin/badges"),
            params={"created_by": "alice,bob"},
        )
        assert by_multi.status_code == 200
        assert by_multi.json()["total"] == 2
        names = {b["name"] for b in by_multi.json()["badges"]}
        assert names == {"Alice Badge", "Bob Badge"}

        # NULL created_by excluded when filter is present.
        assert all(b["created_by"] is not None for b in by_multi.json()["badges"])

    async def test_list_created_date_range_and_invalid(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        await _seed_module(db_session, domain="rmnch")
        await _seed_module(db_session, domain="clinical")

        early = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Early Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/early.png",
                "module_ids": [],
            },
        )
        late = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Late Badge",
                "domain": "clinical",
                "image_storage_path": "badges/late.png",
                "module_ids": [],
            },
        )
        assert early.status_code == 201
        assert late.status_code == 201

        early_row = (await db_session.execute(select(Badge).where(Badge.name == "Early Badge"))).scalar_one()
        late_row = (await db_session.execute(select(Badge).where(Badge.name == "Late Badge"))).scalar_one()
        early_row.created_at = datetime(2025, 1, 15, tzinfo=UTC)
        late_row.created_at = datetime(2025, 6, 15, tzinfo=UTC)
        await db_session.commit()

        in_range = await client.get(
            platform_path("/admin/badges"),
            params={
                "created_from": "2025-01-01T00:00:00Z",
                "created_to": "2025-03-31T23:59:59Z",
            },
        )
        assert in_range.status_code == 200
        assert in_range.json()["total"] == 1
        assert in_range.json()["badges"][0]["name"] == "Early Badge"

        with_domain = await client.get(
            platform_path("/admin/badges"),
            params={
                "domain": "clinical",
                "created_from": "2025-01-01T00:00:00Z",
                "created_to": "2025-12-31T23:59:59Z",
            },
        )
        assert with_domain.status_code == 200
        assert with_domain.json()["total"] == 1
        assert with_domain.json()["badges"][0]["name"] == "Late Badge"

        invalid = await client.get(
            platform_path("/admin/badges"),
            params={
                "created_from": "2025-12-31T00:00:00Z",
                "created_to": "2025-01-01T00:00:00Z",
            },
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "invalid_query"

    async def test_list_module_title_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        antenatal = await _seed_module(db_session, title="Antenatal Care", domain="rmnch")
        postnatal = await _seed_module(db_session, title="Postnatal Visit", domain="rmnch")
        other = await _seed_module(db_session, title="Nutrition Basics", domain="rmnch")

        linked_a = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Antenatal Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/ant.png",
                "module_ids": [str(antenatal.id)],
            },
        )
        linked_p = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Postnatal Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/post.png",
                "module_ids": [str(postnatal.id)],
            },
        )
        unlinked = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Orphan Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/orph.png",
                "module_ids": [str(other.id)],
            },
        )
        assert linked_a.status_code == 201
        assert linked_p.status_code == 201
        assert unlinked.status_code == 201

        by_substring = await client.get(
            platform_path("/admin/badges"),
            params={"module_title": "natal"},
        )
        assert by_substring.status_code == 200
        assert by_substring.json()["total"] == 2
        names = {b["name"] for b in by_substring.json()["badges"]}
        assert names == {"Antenatal Badge", "Postnatal Badge"}

        by_multi_or = await client.get(
            platform_path("/admin/badges"),
            params={"module_title": ["Antenatal", "Nutrition"]},
        )
        assert by_multi_or.status_code == 200
        assert by_multi_or.json()["total"] == 2
        names = {b["name"] for b in by_multi_or.json()["badges"]}
        assert names == {"Antenatal Badge", "Orphan Badge"}

        unknown = await client.get(
            platform_path("/admin/badges"),
            params={"module_title": "does-not-exist-module"},
        )
        assert unknown.status_code == 200
        assert unknown.json()["total"] == 0
        assert unknown.json()["badges"] == []

    async def test_list_created_by_and_module_title_combined(
        self,
        client_with_spice: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        module_a = await _seed_module(db_session, title="Combo Module A", domain="rmnch")
        module_b = await _seed_module(db_session, title="Combo Module B", domain="rmnch")

        match = await client_with_spice.post(
            platform_path("/admin/badges"),
            json={
                "name": "Combo Match",
                "domain": "rmnch",
                "image_storage_path": "badges/combo1.png",
                "module_ids": [str(module_a.id)],
            },
            headers={"X-Test-Username": "alice"},
        )
        # Same creator, different module — filtered out by module_title AND.
        await client_with_spice.post(
            platform_path("/admin/badges"),
            json={
                "name": "Combo Wrong Module",
                "domain": "rmnch",
                "image_storage_path": "badges/combo2.png",
                "module_ids": [str(module_b.id)],
            },
            headers={"X-Test-Username": "alice"},
        )
        # Same module, different creator — filtered out by created_by AND.
        await client_with_spice.post(
            platform_path("/admin/badges"),
            json={
                "name": "Combo Wrong Creator",
                "domain": "rmnch",
                "image_storage_path": "badges/combo3.png",
                "module_ids": [str(module_a.id)],
            },
            headers={"X-Test-Username": "bob"},
        )
        assert match.status_code == 201

        combined = await client_with_spice.get(
            platform_path("/admin/badges"),
            params={"created_by": "alice", "module_title": "Module A"},
        )
        assert combined.status_code == 200
        assert combined.json()["total"] == 1
        assert combined.json()["badges"][0]["name"] == "Combo Match"

    async def test_duplicate_name_conflict(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(db_session, domain="rmnch")
        payload = {
            "name": "Unique Name",
            "domain": "rmnch",
            "image_storage_path": "badges/u.png",
            "module_ids": [],
        }
        first = await client.post(platform_path("/admin/badges"), json=payload)
        assert first.status_code == 201

        second = await client.post(platform_path("/admin/badges"), json=payload)
        assert second.status_code == 409
        assert second.json()["code"] == "badge_name_conflict"

        # Soft-delete frees the name for reuse.
        await client.delete(platform_path(f"/admin/badges/{first.json()['id']}"))
        reused = await client.post(platform_path("/admin/badges"), json=payload)
        assert reused.status_code == 201

    async def test_unknown_domain_rejected(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(db_session, domain="rmnch")
        resp = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "New Domain Badge",
                "domain": "Sample Domain",
                "image_storage_path": "badges/x.png",
                "module_ids": [],
            },
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "badge_domain_invalid"

    async def test_existing_module_domain_normalized_on_create(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_module(db_session, domain="rmnch")
        create = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Domain List Badge",
                "domain": "RMNCH",
                "image_storage_path": "badges/x.png",
                "module_ids": [],
            },
        )
        assert create.status_code == 201
        assert create.json()["domain"] == "rmnch"

    async def test_invalid_domain(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(db_session, domain="rmnch")
        resp = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Bad Domain",
                "domain": "!!!",
                "image_storage_path": "badges/x.png",
                "module_ids": [],
            },
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "badge_domain_invalid"

    async def test_non_published_module_rejected(self, client: AsyncClient, db_session: AsyncSession) -> None:
        draft = await _seed_module(db_session, domain="rmnch", lifecycle_status="draft")
        resp = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Needs Published",
                "domain": "rmnch",
                "image_storage_path": "badges/y.png",
                "module_ids": [str(draft.id)],
            },
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "badge_module_not_published"

    async def test_update_replace_all_module_ids(self, client: AsyncClient, db_session: AsyncSession) -> None:
        m1 = await _seed_module(db_session, title="One", domain="rmnch")
        m2 = await _seed_module(db_session, title="Two", domain="rmnch")
        m3 = await _seed_module(db_session, title="Three", domain="rmnch")

        create = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Replace Modules",
                "domain": "rmnch",
                "image_storage_path": "badges/z.png",
                "module_ids": [str(m1.id), str(m2.id)],
            },
        )
        assert create.status_code == 201
        badge_id = create.json()["id"]

        update = await client.put(
            platform_path(f"/admin/badges/{badge_id}"),
            json={
                "name": "Replace Modules",
                "domain": "rmnch",
                "image_storage_path": "badges/z.png",
                "module_ids": [str(m3.id)],
            },
        )
        assert update.status_code == 200
        assert update.json()["module_ids"] == [str(m3.id)]

    async def test_sequence_round_trip_and_update_semantics(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        await _seed_module(db_session, domain="rmnch")

        omit = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "No Sequence",
                "domain": "rmnch",
                "image_storage_path": "badges/ns.png",
                "module_ids": [],
            },
        )
        assert omit.status_code == 201
        assert omit.json()["sequence"] is None

        create = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Sequenced Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/seq.png",
                "module_ids": [],
                "sequence": 5,
            },
        )
        assert create.status_code == 201
        badge_id = create.json()["id"]
        assert create.json()["sequence"] == 5

        get_resp = await client.get(platform_path(f"/admin/badges/{badge_id}"))
        assert get_resp.status_code == 200
        assert get_resp.json()["sequence"] == 5

        # Omit sequence on PUT — leave prior value unchanged.
        omit_update = await client.put(
            platform_path(f"/admin/badges/{badge_id}"),
            json={
                "name": "Sequenced Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/seq.png",
                "module_ids": [],
            },
        )
        assert omit_update.status_code == 200
        assert omit_update.json()["sequence"] == 5

        # Explicit null clears sequence.
        clear = await client.put(
            platform_path(f"/admin/badges/{badge_id}"),
            json={
                "name": "Sequenced Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/seq.png",
                "module_ids": [],
                "sequence": None,
            },
        )
        assert clear.status_code == 200
        assert clear.json()["sequence"] is None

        # Replace with a new value beyond the former 30 cap.
        set_again = await client.put(
            platform_path(f"/admin/badges/{badge_id}"),
            json={
                "name": "Sequenced Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/seq.png",
                "module_ids": [],
                "sequence": 31,
            },
        )
        assert set_again.status_code == 200
        assert set_again.json()["sequence"] == 31

    async def test_sequence_range_validation(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(db_session, domain="rmnch")
        base = {
            "name": "Range Check",
            "domain": "rmnch",
            "image_storage_path": "badges/range.png",
            "module_ids": [],
        }
        for bad in (0, -1):
            resp = await client.post(platform_path("/admin/badges"), json={**base, "sequence": bad})
            assert resp.status_code == 422, bad

        ok = await client.post(platform_path("/admin/badges"), json={**base, "sequence": 31})
        assert ok.status_code == 201
        assert ok.json()["sequence"] == 31

    async def test_sequence_must_be_unique(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(db_session, domain="rmnch")

        first = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "First Sequence Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/first.png",
                "module_ids": [],
                "sequence": 7,
            },
        )
        assert first.status_code == 201

        second = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Second Sequence Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/second.png",
                "module_ids": [],
                "sequence": 7,
            },
        )
        assert second.status_code == 409
        assert second.json()["code"] == "badge_sequence_conflict"

        cleared = await client.put(
            platform_path(f"/admin/badges/{first.json()['id']}"),
            json={
                "name": "First Sequence Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/first.png",
                "module_ids": [],
                "sequence": None,
            },
        )
        assert cleared.status_code == 200

        retry = await client.post(
            platform_path("/admin/badges"),
            json={
                "name": "Second Sequence Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/second.png",
                "module_ids": [],
                "sequence": 7,
            },
        )
        assert retry.status_code == 201

    async def test_list_sort_by_sequence(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        await _seed_module(db_session, domain="rmnch")

        for name, sequence in (
            ("Seq Two", 2),
            ("Seq Null", None),
            ("Seq One", 1),
        ):
            payload: dict[str, object] = {
                "name": name,
                "domain": "rmnch",
                "image_storage_path": f"badges/{name}.png",
                "module_ids": [],
            }
            if sequence is not None:
                payload["sequence"] = sequence
            resp = await client.post(platform_path("/admin/badges"), json=payload)
            assert resp.status_code == 201

        by_seq = await client.get(
            platform_path("/admin/badges"),
            params={"sort_by": "sequence", "sort_dir": "asc"},
        )
        assert by_seq.status_code == 200
        names = [b["name"] for b in by_seq.json()["badges"]]
        assert names == ["Seq One", "Seq Two", "Seq Null"]

        # Default remains created_at desc (newest first).
        default = await client.get(platform_path("/admin/badges"))
        assert default.status_code == 200
        default_names = [b["name"] for b in default.json()["badges"]]
        assert default_names[0] == "Seq One"

        bad_sort = await client.get(
            platform_path("/admin/badges"),
            params={"sort_by": "name"},
        )
        assert bad_sort.status_code == 422
        assert bad_sort.json()["code"] == "invalid_query"

        bad_dir = await client.get(
            platform_path("/admin/badges"),
            params={"sort_dir": "sideways"},
        )
        assert bad_dir.status_code == 422
        assert bad_dir.json()["code"] == "invalid_query"


@pytest_asyncio.fixture
async def app_with_spice(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    app_obj = FastAPI()
    register_problem_handlers(
        app_obj,
        validation_error_type=RequestValidationError,
        http_exception_type=HTTPException,
    )

    @app_obj.middleware("http")
    async def inject_spice_user(request: Request, call_next):  # type: ignore[no-untyped-def]
        username = request.headers.get("X-Test-Username", "badge_admin")
        request.state.spice_user = SpiceUserContext.model_validate({"id": 42, "username": username})
        request.state.selected_tenant_id = 1
        return await call_next(request)

    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(badges_router)
    app_obj.include_router(api_router)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app_obj.dependency_overrides[get_db] = _override_get_db
    yield app_obj
    app_obj.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_with_spice(app_with_spice: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app_with_spice)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestAdminBadgesAuditActors:
    async def test_created_by_and_updated_by_from_spice_user(
        self,
        client_with_spice: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        module = await _seed_module(db_session, domain="rmnch")

        create = await client_with_spice.post(
            platform_path("/admin/badges"),
            json={
                "name": "Audited Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/audit.png",
                "module_ids": [str(module.id)],
            },
            headers={"X-Test-Username": "creator_user"},
        )
        assert create.status_code == 201
        created = create.json()
        badge_id = created["id"]
        assert created["created_by"] == "creator_user"
        assert created["updated_by"] == "creator_user"

        update = await client_with_spice.put(
            platform_path(f"/admin/badges/{badge_id}"),
            json={
                "name": "Audited Badge",
                "domain": "rmnch",
                "image_storage_path": "badges/audit2.png",
                "module_ids": [str(module.id)],
            },
            headers={"X-Test-Username": "editor_user"},
        )
        assert update.status_code == 200
        updated = update.json()
        assert updated["created_by"] == "creator_user"
        assert updated["updated_by"] == "editor_user"

        delete = await client_with_spice.delete(
            platform_path(f"/admin/badges/{badge_id}"),
            headers={"X-Test-Username": "deleter_user"},
        )
        assert delete.status_code == 204

        row = (await db_session.execute(select(Badge).where(Badge.id == UUID(badge_id)))).scalar_one()
        assert row.created_by == "creator_user"
        assert row.updated_by == "deleter_user"
