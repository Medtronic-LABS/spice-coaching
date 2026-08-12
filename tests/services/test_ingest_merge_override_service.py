"""Tests for admin ingest merge override-merge service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from mc_foundation.problem import AppError
from platform_service.db.module_availability import (
    LIFECYCLE_DRAFT,
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_RETIRED,
    LIFECYCLE_REVIEW_PENDING,
)
from platform_service.services.ingest_merge_override_service import IngestMergeOverrideService
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_override_promotes_secondary_and_retires_primary_and_source() -> None:
    primary_id = uuid4()
    secondary_id = uuid4()
    source_id = uuid4()
    family_id = uuid4()

    primary = MagicMock(
        id=primary_id,
        merge_secondary_module_id=secondary_id,
        merge_source_module_id=source_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
    )
    secondary = MagicMock(
        id=secondary_id,
        module_family_id=family_id,
        version=2,
        merge_primary_module_id=primary_id,
        merge_source_module_id=source_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
        supersedes_module_id=None,
    )
    source = MagicMock(id=source_id, lifecycle_status=LIFECYCLE_PUBLISHED)
    family = MagicMock(id=family_id, current_published_module_id=source_id)

    session = AsyncMock()
    session.get = AsyncMock(side_effect=[primary, secondary, source, family])
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    service = IngestMergeOverrideService(session)
    service._modules = MagicMock()
    service._modules.retire_module = AsyncMock(side_effect=[primary, source])
    service._modules.next_version_in_family = AsyncMock(return_value=4)

    result = await service.override(primary_id)

    assert result.primary_module_id == primary_id
    assert result.secondary_module_id == secondary_id
    assert result.source_module_id == source_id
    assert result.secondary_lifecycle_status == LIFECYCLE_DRAFT
    assert secondary.lifecycle_status == LIFECYCLE_DRAFT
    assert secondary.supersedes_module_id == source_id
    assert secondary.version == 4
    assert family.current_published_module_id == secondary_id
    assert service._modules.retire_module.await_count == 2
    service._modules.next_version_in_family.assert_awaited_once_with(family_id)
    session.flush.assert_awaited()
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_override_version_conflict_on_flush() -> None:
    primary_id = uuid4()
    secondary_id = uuid4()
    source_id = uuid4()
    family_id = uuid4()
    tip_id = uuid4()

    primary = MagicMock(
        id=primary_id,
        merge_secondary_module_id=secondary_id,
        merge_source_module_id=source_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
    )
    secondary = MagicMock(
        id=secondary_id,
        module_family_id=family_id,
        version=2,
        merge_primary_module_id=primary_id,
        merge_source_module_id=source_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
        supersedes_module_id=None,
    )
    source = MagicMock(id=source_id, lifecycle_status=LIFECYCLE_PUBLISHED)
    family = MagicMock(id=family_id, current_published_module_id=source_id)
    tip = MagicMock(id=tip_id, version=5)

    session = AsyncMock()
    session.get = AsyncMock(side_effect=[primary, secondary, source, family])
    session.flush = AsyncMock(side_effect=IntegrityError("stmt", "params", "orig"))
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    service = IngestMergeOverrideService(session)
    service._modules = MagicMock()
    service._modules.retire_module = AsyncMock(side_effect=[primary, source])
    service._modules.next_version_in_family = AsyncMock(return_value=4)
    service._modules.latest_module_in_family = AsyncMock(return_value=tip)

    with pytest.raises(AppError) as exc_info:
        await service.override(primary_id)

    assert exc_info.value.code == "module_version_conflict"
    assert exc_info.value.status == 409
    assert exc_info.value.extensions == {
        "expected_version": 2,
        "current_version": 5,
        "latest_module_id": str(tip_id),
    }
    session.rollback.assert_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_override_rejects_non_primary() -> None:
    module_id = uuid4()
    module = MagicMock(
        id=module_id,
        merge_secondary_module_id=None,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=module)

    with pytest.raises(AppError) as exc_info:
        await IngestMergeOverrideService(session).override(module_id)
    assert exc_info.value.code == "merge_override_not_primary"
    assert exc_info.value.status == 400


@pytest.mark.asyncio
async def test_override_rejects_when_not_review_pending() -> None:
    primary_id = uuid4()
    primary = MagicMock(
        id=primary_id,
        merge_secondary_module_id=uuid4(),
        lifecycle_status=LIFECYCLE_DRAFT,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=primary)

    with pytest.raises(AppError) as exc_info:
        await IngestMergeOverrideService(session).override(primary_id)
    assert exc_info.value.code == "merge_override_not_review_pending"
    assert exc_info.value.status == 409


@pytest.mark.asyncio
async def test_override_rejects_when_source_retired() -> None:
    primary_id = uuid4()
    secondary_id = uuid4()
    source_id = uuid4()
    primary = MagicMock(
        id=primary_id,
        merge_secondary_module_id=secondary_id,
        merge_source_module_id=source_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
    )
    secondary = MagicMock(
        id=secondary_id,
        merge_source_module_id=source_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
    )
    source = MagicMock(id=source_id, lifecycle_status=LIFECYCLE_RETIRED)

    session = AsyncMock()
    session.get = AsyncMock(side_effect=[primary, secondary, source])

    with pytest.raises(AppError) as exc_info:
        await IngestMergeOverrideService(session).override(primary_id)
    assert exc_info.value.code == "merge_override_source_unavailable"
    assert exc_info.value.status == 409
