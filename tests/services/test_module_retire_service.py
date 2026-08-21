"""Tests for ModuleRetireService dual-path secondary cascade."""

from __future__ import annotations

from uuid import uuid4

import pytest
from platform_service.db.repositories.module_repository import ModuleNotFoundError
from platform_service.services.module_retire_service import ModuleRetireService
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.conftest import _make_family, _make_module
from tests.helpers.hierarchy_fixtures import AM_ID, PO_ID, seed_basic_hierarchy


@pytest.mark.asyncio
class TestModuleRetireService:
    async def test_retires_primary_and_secondary(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        source = await _make_module(db_session, family=fam, title_localized={"bn": "source"}, version=1)
        secondary = await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_localized={"bn": "secondary"},
            version=1,
            lifecycle_status="review_pending",
            set_family_pointer=False,
        )
        primary = await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_localized={"bn": "primary"},
            version=1,
            lifecycle_status="review_pending",
            set_family_pointer=False,
        )
        primary.merge_secondary_module_id = secondary.id
        primary.merge_source_module_id = source.id
        secondary.merge_primary_module_id = primary.id
        secondary.merge_source_module_id = source.id
        await db_session.flush()

        out = await ModuleRetireService(db_session).retire(primary.id)

        assert out.id == primary.id
        assert out.lifecycle_status == "retired"
        assert out.retired_at is not None
        await db_session.refresh(secondary)
        await db_session.refresh(source)
        assert secondary.lifecycle_status == "retired"
        assert secondary.retired_at is not None
        assert source.lifecycle_status == "published"
        assert primary.module_family_id != secondary.module_family_id

    async def test_retires_module_without_secondary(self, db_session: AsyncSession) -> None:
        m = await _make_module(db_session, title_localized={"bn": "solo"})

        out = await ModuleRetireService(db_session).retire(m.id)

        assert out.lifecycle_status == "retired"
        assert out.merge_secondary_module_id is None

    async def test_retiring_secondary_does_not_retire_primary(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        primary = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "primary"},
            version=1,
            lifecycle_status="review_pending",
            set_family_pointer=False,
        )
        secondary = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "secondary"},
            version=2,
            lifecycle_status="review_pending",
            set_family_pointer=False,
        )
        primary.merge_secondary_module_id = secondary.id
        secondary.merge_primary_module_id = primary.id
        await db_session.flush()

        out = await ModuleRetireService(db_session).retire(secondary.id)

        assert out.id == secondary.id
        assert out.lifecycle_status == "retired"
        await db_session.refresh(primary)
        assert primary.lifecycle_status == "review_pending"

    async def test_missing_secondary_still_retires_primary(self, db_session: AsyncSession) -> None:
        primary = await _make_module(
            db_session,
            title_localized={"bn": "primary"},
            lifecycle_status="review_pending",
            set_family_pointer=False,
        )
        primary.merge_secondary_module_id = uuid4()
        await db_session.flush()

        out = await ModuleRetireService(db_session).retire(primary.id)

        assert out.lifecycle_status == "retired"

    async def test_already_retired_secondary_is_ok(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        secondary = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "secondary"},
            version=1,
            lifecycle_status="retired",
            set_family_pointer=False,
        )
        primary = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "primary"},
            version=2,
            lifecycle_status="review_pending",
            set_family_pointer=False,
        )
        primary.merge_secondary_module_id = secondary.id
        await db_session.flush()

        out = await ModuleRetireService(db_session).retire(primary.id)

        assert out.lifecycle_status == "retired"
        await db_session.refresh(secondary)
        assert secondary.lifecycle_status == "retired"

    async def test_retire_stamps_retired_by_on_primary_and_secondary(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        fam = await _make_family(db_session)
        secondary = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "secondary"},
            version=1,
            lifecycle_status="review_pending",
            set_family_pointer=False,
        )
        primary = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "primary"},
            version=2,
            lifecycle_status="review_pending",
            set_family_pointer=False,
        )
        primary.merge_secondary_module_id = secondary.id
        await db_session.flush()

        out = await ModuleRetireService(db_session).retire(primary.id, retired_by_user_id=PO_ID)

        assert out.retired_by == PO_ID
        await db_session.refresh(secondary)
        assert secondary.retired_by == PO_ID

    async def test_already_retired_secondary_keeps_original_retired_by(
        self, db_session: AsyncSession
    ) -> None:
        await seed_basic_hierarchy(db_session)
        fam = await _make_family(db_session)
        secondary = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "secondary"},
            version=1,
            lifecycle_status="retired",
            set_family_pointer=False,
        )
        secondary.retired_by = AM_ID
        primary = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "primary"},
            version=2,
            lifecycle_status="review_pending",
            set_family_pointer=False,
        )
        primary.merge_secondary_module_id = secondary.id
        await db_session.flush()

        await ModuleRetireService(db_session).retire(primary.id, retired_by_user_id=PO_ID)

        await db_session.refresh(secondary)
        assert secondary.retired_by == AM_ID

    async def test_unknown_module_raises(self, db_session: AsyncSession) -> None:
        with pytest.raises(ModuleNotFoundError):
            await ModuleRetireService(db_session).retire(uuid4())
