"""Soft user refs: orphan retention when hierarchy users are deleted."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_foundation.problem import register_problem_handlers
from platform_service.api.modules import router as modules_router
from platform_service.auth.spice_context import SpiceUserContext
from platform_service.config import get_settings
from platform_service.db.models.hierarchy_user import HierarchyUser
from platform_service.db.models.module import Module
from platform_service.db.models.module_assignment import ModuleAssignment
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.module_availability import LIFECYCLE_PUBLISHED
from platform_service.deps import get_db
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import platform_path, requires_db
from tests.helpers.hierarchy_fixtures import AM_ID, SK_ID, seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data_between_tests(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text(
            "TRUNCATE module_assignment, module, module_family, "
            '"users", user_upazila, upazila, district, division RESTART IDENTITY CASCADE'
        )
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

    @app_obj.middleware("http")
    async def inject_spice_user(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.spice_user = SpiceUserContext.model_validate({"id": AM_ID, "username": "am"})
        request.state.selected_tenant_id = 0
        return await call_next(request)

    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(modules_router)
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


async def test_deleted_user_leaves_assignment_and_null_actor_dto(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Soft refs keep orphan bigints; API actor DTOs become null when user is gone."""
    await seed_basic_hierarchy(db_session)

    family = ModuleFamily(module_code="ORPHAN-SOFT-REF", tenant_id=0, created_by=AM_ID)
    db_session.add(family)
    await db_session.flush()

    module = Module(
        id=uuid4(),
        module_family_id=family.id,
        version=1,
        title_localized={"en": "Orphan Soft Ref"},
        domain="clinical",
        module_type="refresher",
        tenant_id=0,
        lifecycle_status=LIFECYCLE_PUBLISHED,
        module_json={},
        created_by=AM_ID,
    )
    db_session.add(module)
    await db_session.flush()

    assignment = ModuleAssignment(
        module_id=module.id,
        tenant_id=0,
        user_id=SK_ID,
        assigned_by=AM_ID,
    )
    db_session.add(assignment)
    await db_session.commit()

    # Delete SK (relationship target) and AM (stamper) without cascading soft refs.
    await db_session.execute(delete(HierarchyUser).where(HierarchyUser.id == SK_ID))
    await db_session.execute(delete(HierarchyUser).where(HierarchyUser.id == AM_ID))
    await db_session.commit()

    remaining = (
        await db_session.execute(select(ModuleAssignment).where(ModuleAssignment.module_id == module.id))
    ).scalar_one()
    assert remaining.user_id == SK_ID
    assert remaining.assigned_by == AM_ID

    stamped = (await db_session.execute(select(Module).where(Module.id == module.id))).scalar_one()
    assert stamped.created_by == AM_ID

    resp = await client.get(platform_path(f"/admin/modules/{module.id}"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_by"] is None
