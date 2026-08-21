"""Tests for admin ingest merge override-merge service."""

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

from tests.helpers.hierarchy_fixtures import PO_ID


@pytest.mark.asyncio
async def test_override_promotes_secondary_and_retires_primary_and_source() -> None:
    primary_id = uuid4()
    secondary_id = uuid4()
    source_id = uuid4()
    primary_family_id = uuid4()
    secondary_family_id = uuid4()
    source_family_id = uuid4()

    primary = MagicMock(
        id=primary_id,
        merge_secondary_module_id=secondary_id,
        merge_source_module_id=source_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
        version=1,
        module_family_id=primary_family_id,
    )
    secondary = MagicMock(
        id=secondary_id,
        module_family_id=secondary_family_id,
        version=1,
        merge_primary_module_id=primary_id,
        merge_source_module_id=source_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
        supersedes_module_id=None,
    )
    source = MagicMock(
        id=source_id,
        lifecycle_status=LIFECYCLE_PUBLISHED,
        module_family_id=source_family_id,
    )
    source_family = MagicMock(id=source_family_id, current_published_module_id=source_id)

    session = AsyncMock()
    session.get = AsyncMock(side_effect=[primary, secondary, source, source_family])
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    service = IngestMergeOverrideService(session)
    service._modules = MagicMock()
    service._modules.retire_module = AsyncMock(side_effect=[primary, source])

    result = await service.override(primary_id, retired_by_user_id=PO_ID)

    assert result.primary_module_id == primary_id
    assert result.secondary_module_id == secondary_id
    assert result.source_module_id == source_id
    assert result.secondary_lifecycle_status == LIFECYCLE_DRAFT
    assert secondary.lifecycle_status == LIFECYCLE_DRAFT
    assert secondary.supersedes_module_id == source_id
    assert secondary.version == 1
    assert secondary.module_family_id == secondary_family_id
    assert source_family.current_published_module_id is None
    assert service._modules.retire_module.await_count == 2
    service._modules.retire_module.assert_any_await(primary.id, retired_by_user_id=PO_ID)
    service._modules.retire_module.assert_any_await(source.id, retired_by_user_id=PO_ID)
    session.flush.assert_awaited()
    session.commit.assert_awaited()


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
async def test_override_succeeds_when_source_already_retired() -> None:
    primary_id = uuid4()
    secondary_id = uuid4()
    source_id = uuid4()
    primary_family_id = uuid4()
    secondary_family_id = uuid4()
    source_family_id = uuid4()

    primary = MagicMock(
        id=primary_id,
        merge_secondary_module_id=secondary_id,
        merge_source_module_id=source_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
        version=1,
        module_family_id=primary_family_id,
    )
    secondary = MagicMock(
        id=secondary_id,
        module_family_id=secondary_family_id,
        version=1,
        merge_primary_module_id=primary_id,
        merge_source_module_id=source_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
        supersedes_module_id=None,
    )
    source = MagicMock(
        id=source_id,
        lifecycle_status=LIFECYCLE_RETIRED,
        module_family_id=source_family_id,
    )
    source_family = MagicMock(id=source_family_id, current_published_module_id=None)

    session = AsyncMock()
    session.get = AsyncMock(side_effect=[primary, secondary, source, source_family])
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    service = IngestMergeOverrideService(session)
    service._modules = MagicMock()
    service._modules.retire_module = AsyncMock(side_effect=[primary, source])

    result = await service.override(primary_id, retired_by_user_id=PO_ID)

    assert result.source_module_id == source_id
    assert result.secondary_lifecycle_status == LIFECYCLE_DRAFT
    assert secondary.supersedes_module_id == source_id
    assert secondary.version == 1
    service._modules.retire_module.assert_any_await(source.id, retired_by_user_id=PO_ID)
