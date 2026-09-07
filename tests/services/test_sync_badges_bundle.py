"""Tests for BadgesBundleBuilder sync service."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from mc_foundation.objectstore import ObjectStorageError
from platform_service.db.repositories.badge_repository import BadgeRepository
from platform_service.db.repositories.chw_badge_repository import CHWBadgeRepository
from platform_service.services.sync.badges_bundle_builder import BadgesBundleBuilder
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data_between_tests(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(text("TRUNCATE chw_badge, badge_module, badge RESTART IDENTITY CASCADE"))
    await db_session.commit()


class _FakeStorage:
    bucket_name = "medtronics-storage"

    async def presigned_get_url(self, object_name: str, **kwargs):  # type: ignore[no-untyped-def]
        if "invalid" in object_name:
            raise ObjectStorageError("presign failed")
        return type("Url", (), {"url": f"https://example.test/{object_name}", "expires_seconds": 3600})()


class TestBadgesBundleBuilder:
    async def test_tenant_isolation_and_soft_delete(self, db_session: AsyncSession) -> None:
        badge_repo = BadgeRepository(db_session)
        chw_repo = CHWBadgeRepository(db_session)

        # Tenant 1 active badge
        b1 = await badge_repo.create(
            name="Tenant 1 Badge",
            domain="clinical",
            image_storage_path="medtronics-storage/badges/b1.png",
            tenant_id=1,
            sequence=1,
        )

        # Tenant 2 active badge
        await badge_repo.create(
            name="Tenant 2 Badge",
            domain="digital",
            image_storage_path="medtronics-storage/badges/b2.png",
            tenant_id=2,
            sequence=1,
        )

        # Tenant 1 soft-deleted badge
        b3 = await badge_repo.create(
            name="Soft Deleted Badge",
            domain="clinical",
            image_storage_path="medtronics-storage/badges/b3.png",
            tenant_id=1,
            sequence=2,
        )
        await badge_repo.soft_delete(b3)

        # Award b1 and b3 to CHW 101 in tenant 1
        await chw_repo.try_insert_award(chw_id=101, badge_id=b1.id, tenant_id=1)
        await chw_repo.try_insert_award(chw_id=101, badge_id=b3.id, tenant_id=1)

        builder = BadgesBundleBuilder(db_session)
        storage = _FakeStorage()

        # Build bundle for CHW 101 in tenant 1
        bundle = await builder.build(user_id=101, tenant_id=1, storage=storage)  # type: ignore[arg-type]

        # Available badges should contain b1 only (active, tenant 1)
        avail_ids = [b.id for b in bundle.available_badges]
        assert avail_ids == [b1.id]
        assert bundle.available_badges[0].image_storage_path == "badges/b1.png"

        # Earned badges should contain both b1 and b3 (soft-deleted included)
        earned_ids = [b.id for b in bundle.earned_badges]
        assert set(earned_ids) == {b1.id, b3.id}
        assert {b.image_storage_path for b in bundle.earned_badges} == {
            "badges/b1.png",
            "badges/b3.png",
        }

    async def test_unearned_chw_gets_empty_earned(self, db_session: AsyncSession) -> None:
        badge_repo = BadgeRepository(db_session)
        b1 = await badge_repo.create(
            name="Active Badge",
            domain="clinical",
            image_storage_path="medtronics-storage/badges/b1.png",
            tenant_id=1,
        )

        builder = BadgesBundleBuilder(db_session)
        storage = _FakeStorage()

        bundle = await builder.build(user_id=999, tenant_id=1, storage=storage)  # type: ignore[arg-type]
        assert len(bundle.available_badges) == 1
        assert bundle.available_badges[0].id == b1.id
        assert bundle.earned_badges == []

    async def test_module_ids_and_presign_soft_fail(self, db_session: AsyncSession) -> None:
        badge_repo = BadgeRepository(db_session)
        b1 = await badge_repo.create(
            name="Linked Badge",
            domain="clinical",
            image_storage_path="invalid_path_no_bucket.png",
            tenant_id=1,
        )

        # Link module IDs
        mod_id = uuid.uuid4()
        await badge_repo.replace_module_links(b1.id, [mod_id])

        builder = BadgesBundleBuilder(db_session)
        storage = _FakeStorage()

        bundle = await builder.build(user_id=1, tenant_id=1, storage=storage)  # type: ignore[arg-type]
        assert len(bundle.available_badges) == 1
        payload = bundle.available_badges[0]
        assert payload.module_ids == [mod_id]
        assert payload.image_storage_path == "invalid_path_no_bucket.png"
        # Invalid path presign should soft-fail to None
        assert payload.image_presigned_url is None
