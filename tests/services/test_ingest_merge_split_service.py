"""Tests for admin ingest merge split-merge service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from mc_foundation.problem import AppError
from platform_service.db.module_availability import (
    LIFECYCLE_DRAFT,
    LIFECYCLE_RETIRED,
    LIFECYCLE_REVIEW_PENDING,
)
from platform_service.services.ingest_merge_split_service import IngestMergeSplitService

from tests.helpers.hierarchy_fixtures import PO_ID


@pytest.mark.asyncio
async def test_split_keeps_primary_draft_and_retires_secondary() -> None:
    primary_id = uuid4()
    secondary_id = uuid4()
    source_id = uuid4()
    primary_family_id = uuid4()
    secondary_family_id = uuid4()

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

    session = AsyncMock()
    session.get = AsyncMock(side_effect=[primary, secondary])
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    async def _retire(module_id, *, retired_by_user_id=None):
        assert module_id == secondary_id
        assert retired_by_user_id == PO_ID
        secondary.lifecycle_status = LIFECYCLE_RETIRED
        return secondary

    service = IngestMergeSplitService(session)
    service._modules = MagicMock()
    service._modules.retire_module = AsyncMock(side_effect=_retire)

    result = await service.split(primary_id, retired_by_user_id=PO_ID)

    assert result.primary_module_id == primary_id
    assert result.secondary_module_id == secondary_id
    assert result.source_module_id == source_id
    assert result.primary_lifecycle_status == LIFECYCLE_DRAFT
    assert result.secondary_lifecycle_status == LIFECYCLE_RETIRED
    assert primary.lifecycle_status == LIFECYCLE_DRAFT
    assert primary.merge_secondary_module_id == secondary_id
    assert primary.merge_source_module_id == source_id
    assert primary.version == 1
    assert secondary.merge_primary_module_id == primary_id
    assert secondary.merge_source_module_id == source_id
    assert secondary.version == 1
    assert secondary.supersedes_module_id is None
    service._modules.retire_module.assert_awaited_once_with(
        secondary.id,
        retired_by_user_id=PO_ID,
    )
    assert session.get.await_count == 2
    session.flush.assert_awaited()
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_split_succeeds_when_source_link_missing() -> None:
    primary_id = uuid4()
    secondary_id = uuid4()

    primary = MagicMock(
        id=primary_id,
        merge_secondary_module_id=secondary_id,
        merge_source_module_id=None,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
        version=2,
    )
    secondary = MagicMock(
        id=secondary_id,
        merge_primary_module_id=primary_id,
        merge_source_module_id=None,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
        version=1,
    )

    session = AsyncMock()
    session.get = AsyncMock(side_effect=[primary, secondary])
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    async def _retire(module_id, *, retired_by_user_id=None):
        secondary.lifecycle_status = LIFECYCLE_RETIRED
        return secondary

    service = IngestMergeSplitService(session)
    service._modules = MagicMock()
    service._modules.retire_module = AsyncMock(side_effect=_retire)

    result = await service.split(primary_id)

    assert result.source_module_id is None
    assert result.primary_lifecycle_status == LIFECYCLE_DRAFT
    assert result.secondary_lifecycle_status == LIFECYCLE_RETIRED
    service._modules.retire_module.assert_awaited_once()


@pytest.mark.asyncio
async def test_split_rejects_missing_module() -> None:
    module_id = uuid4()
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc_info:
        await IngestMergeSplitService(session).split(module_id)
    assert exc_info.value.code == "module_not_found"
    assert exc_info.value.status == 404


@pytest.mark.asyncio
async def test_split_rejects_non_primary() -> None:
    module_id = uuid4()
    module = MagicMock(
        id=module_id,
        merge_secondary_module_id=None,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=module)

    with pytest.raises(AppError) as exc_info:
        await IngestMergeSplitService(session).split(module_id)
    assert exc_info.value.code == "merge_split_not_primary"
    assert exc_info.value.status == 400


@pytest.mark.asyncio
async def test_split_rejects_when_not_review_pending() -> None:
    primary_id = uuid4()
    primary = MagicMock(
        id=primary_id,
        merge_secondary_module_id=uuid4(),
        lifecycle_status=LIFECYCLE_DRAFT,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=primary)

    with pytest.raises(AppError) as exc_info:
        await IngestMergeSplitService(session).split(primary_id)
    assert exc_info.value.code == "merge_split_not_review_pending"
    assert exc_info.value.status == 409


@pytest.mark.asyncio
async def test_split_rejects_when_secondary_missing() -> None:
    primary_id = uuid4()
    secondary_id = uuid4()
    primary = MagicMock(
        id=primary_id,
        merge_secondary_module_id=secondary_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
    )
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[primary, None])

    with pytest.raises(AppError) as exc_info:
        await IngestMergeSplitService(session).split(primary_id)
    assert exc_info.value.code == "module_not_found"
    assert exc_info.value.status == 404


@pytest.mark.asyncio
async def test_split_rejects_when_secondary_not_review_pending() -> None:
    primary_id = uuid4()
    secondary_id = uuid4()
    primary = MagicMock(
        id=primary_id,
        merge_secondary_module_id=secondary_id,
        lifecycle_status=LIFECYCLE_REVIEW_PENDING,
    )
    secondary = MagicMock(
        id=secondary_id,
        lifecycle_status=LIFECYCLE_DRAFT,
    )
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[primary, secondary])

    with pytest.raises(AppError) as exc_info:
        await IngestMergeSplitService(session).split(primary_id)
    assert exc_info.value.code == "merge_split_secondary_unavailable"
    assert exc_info.value.status == 409
