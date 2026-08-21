"""Unit tests for frozen ingestion-run generation count helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from platform_service.db.models.ingestion_run import IngestionRunStep
from platform_service.services.ingestion_run_generation_counts import (
    primary_module_ids_from_card_draft_steps,
)
from platform_service.services.run_state_service import STAGE_CARD_DRAFT


def _step(
    *,
    module_id: str | None,
    secondary_module_id: str | None = None,
    stage: str = STAGE_CARD_DRAFT,
) -> IngestionRunStep:
    summary: dict[str, object] = {}
    if module_id is not None:
        summary["module_id"] = module_id
    if secondary_module_id is not None:
        summary["secondary_module_id"] = secondary_module_id
    return IngestionRunStep(
        id=uuid4(),
        ingestion_run_id=uuid4(),
        stage=stage,
        status="succeeded",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        output_summary_jsonb=summary or None,
    )


def test_primary_module_ids_dedupes_and_skips_null() -> None:
    primary = uuid4()
    other = uuid4()
    steps = [
        _step(module_id=str(primary)),
        _step(module_id=str(other)),
        _step(module_id=str(primary)),
        _step(module_id=None),
        _step(module_id=str(uuid4()), stage="extract"),
    ]
    assert primary_module_ids_from_card_draft_steps(steps) == [primary, other]


def test_primary_module_ids_excludes_secondary() -> None:
    primary = uuid4()
    secondary = uuid4()
    steps = [
        _step(module_id=str(primary), secondary_module_id=str(secondary)),
        _step(module_id=str(secondary)),
    ]
    assert primary_module_ids_from_card_draft_steps(steps) == [primary]
