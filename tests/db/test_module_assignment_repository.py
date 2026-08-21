"""ModuleAssignmentRepository — in-range assignment batch query."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from platform_service.db.models.module_assignment import ModuleAssignment
from platform_service.db.repositories.module_assignment_repository import ModuleAssignmentRepository
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.db.conftest import _make_module

pytestmark = [requires_db, pytest.mark.asyncio]


async def test_list_module_ids_assigned_in_range_empty_chw_ids(db_session: AsyncSession) -> None:
    repo = ModuleAssignmentRepository(db_session)
    out = await repo.list_module_ids_assigned_in_range_for_chws(
        chw_ids=[],
        tenant_id=1,
        from_ts=datetime(2026, 1, 1, tzinfo=UTC),
        to_ts=datetime(2026, 1, 31, 23, 59, 59, tzinfo=UTC),
    )
    assert out == {}


async def test_list_module_ids_assigned_in_range_filters_by_assigned_at(
    db_session: AsyncSession,
) -> None:
    module_in = await _make_module(db_session)
    module_out = await _make_module(db_session)
    module_faq = await _make_module(db_session)
    module_faq.chatbot_faqs_only = True

    chw_a = uuid4().int % (10**15) + 1
    chw_b = uuid4().int % (10**15) + 2
    in_window = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    before_window = datetime(2025, 12, 1, tzinfo=UTC)

    db_session.add_all(
        [
            ModuleAssignment(
                module_id=module_in.id,
                user_id=chw_a,
                assigned_by=1,
                tenant_id=1,
                assigned_at=in_window,
            ),
            ModuleAssignment(
                module_id=module_out.id,
                user_id=chw_a,
                assigned_by=1,
                tenant_id=1,
                assigned_at=before_window,
            ),
            ModuleAssignment(
                module_id=module_faq.id,
                user_id=chw_a,
                assigned_by=1,
                tenant_id=1,
                assigned_at=in_window,
            ),
            ModuleAssignment(
                module_id=module_in.id,
                user_id=chw_b,
                assigned_by=1,
                tenant_id=1,
                assigned_at=in_window + timedelta(days=1),
            ),
        ]
    )
    await db_session.flush()

    repo = ModuleAssignmentRepository(db_session)
    out = await repo.list_module_ids_assigned_in_range_for_chws(
        chw_ids=[chw_a, chw_b],
        tenant_id=1,
        from_ts=datetime(2026, 1, 1, tzinfo=UTC),
        to_ts=datetime(2026, 1, 31, 23, 59, 59, 999999, tzinfo=UTC),
    )

    assert out[chw_a] == {module_in.id}
    assert out[chw_b] == {module_in.id}
    assert chw_a in out
    assert module_out.id not in out[chw_a]
    assert module_faq.id not in out[chw_a]
