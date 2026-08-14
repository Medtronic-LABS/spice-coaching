"""Tests for ingest worker crash recovery marking source documents failed."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from platform_service.db.models.ingestion_run import IngestionRun
from platform_service.db.models.source_document import SourceDocument
from platform_service.services.run_state_service import RUN_RUNNING
from platform_service.workers.ingest_worker import _mark_active_ingest_failed
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def _wipe(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text("TRUNCATE source_document, ingestion_run_step, ingestion_run RESTART IDENTITY CASCADE")
    )
    await db_session.commit()


async def test_mark_active_ingest_failed_marks_source_document_failed(db_session: AsyncSession) -> None:
    sd = SourceDocument(
        title="crash-test",
        source_type="pdf",
        primary_language="en",
        content_domain="clinical",
        original_storage_path="/tmp/x.pdf",
        status="ingesting",
        tenant_id=1,
    )
    db_session.add(sd)
    await db_session.flush()
    run = IngestionRun(source_document_id=sd.id, status=RUN_RUNNING)
    db_session.add(run)
    await db_session.commit()

    await _mark_active_ingest_failed(sd.id)

    await db_session.refresh(sd)
    await db_session.refresh(run)
    assert sd.status == "failed"
    assert run.status == "failed"
