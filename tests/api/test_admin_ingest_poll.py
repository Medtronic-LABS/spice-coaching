"""Unit tests for admin ingest poll serialisation helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from platform_service.services.ingestion_run_presenter import IngestionRunPresenter
from platform_service.services.run_state_service import (
    RUN_RUNNING,
    RUN_SUCCEEDED,
    STAGE_CANDIDATE_MERGE,
    STAGE_CARD_DRAFT,
    STEP_RUNNING,
    STEP_SUCCEEDED,
)


def _step(
    *,
    stage: str = STAGE_CARD_DRAFT,
    status: str = STEP_RUNNING,
    input_summary: dict | None = None,
    output_summary: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        stage=stage,
        status=status,
        started_at=datetime.now(UTC),
        completed_at=None,
        input_summary_jsonb=input_summary,
        output_summary_jsonb=output_summary,
        error_jsonb=None,
        error_code=None,
        error_message=None,
    )


class TestPresentRunError:
    def test_none_error_jsonb(self) -> None:
        assert IngestionRunPresenter._present_run_error(None) is None

    def test_strips_pipeline_claim(self) -> None:
        assert IngestionRunPresenter._present_run_error(
            {"_pipeline_claim": {"claim_token": "x"}, "failed_stage": "extract"}
        ) == {
            "failed_stage": "extract",
            "message": "Extracting content failed.",
        }

    def test_non_object_error_jsonb_returns_none(self) -> None:
        # Legacy array corruption from jsonb || must not crash list/detail APIs.
        assert (
            IngestionRunPresenter._present_run_error([None, {"_pipeline_claim": {"claim_token": "x"}}])
            is None
        )


class TestRunKind:
    def test_pipeline_by_default(self) -> None:
        run = SimpleNamespace(error_jsonb=None)
        assert IngestionRunPresenter.run_kind(run) == "pipeline"

    def test_historical_fusion_type_is_pipeline(self) -> None:
        run = SimpleNamespace(error_jsonb={"type": "cross_source_fusion"})
        assert IngestionRunPresenter.run_kind(run) == "pipeline"

    def test_non_object_error_jsonb_is_pipeline(self) -> None:
        # Corrupted / legacy array values must not crash poll serialisation.
        run = SimpleNamespace(error_jsonb=[{"_pipeline_claim": {"claim_token": "x"}}])
        assert IngestionRunPresenter.run_kind(run) == "pipeline"


class TestStepToPollDict:
    def test_running_merge_activity(self) -> None:
        cand = str(uuid4())
        step = _step(
            input_summary={
                "activity": "published_module_merge",
                "candidate_id": cand,
            },
        )
        out = IngestionRunPresenter.step_to_poll_dict(step)
        assert out["activity"] == "published_module_merge"
        assert "published_module_merge" not in out

    def test_terminal_card_draft_merge_outcome(self) -> None:
        merged_from = str(uuid4())
        primary = str(uuid4())
        secondary = str(uuid4())
        step = _step(
            status=STEP_SUCCEEDED,
            input_summary={"candidate_id": str(uuid4())},
            output_summary={
                "was_published_merge": True,
                "merged_from_module_id": merged_from,
                "module_id": primary,
                "secondary_module_id": secondary,
            },
        )
        out = IngestionRunPresenter.step_to_poll_dict(step)
        assert out["published_module_merge"] == {
            "active": False,
            "was_merge": True,
            "merged_from_module_id": merged_from,
            "primary_module_id": primary,
            "secondary_module_id": secondary,
        }


class TestCurrentActivityFromSteps:
    def test_published_module_merge(self) -> None:
        cand = str(uuid4())
        steps = [
            _step(
                input_summary={
                    "activity": "published_module_merge",
                    "candidate_id": cand,
                },
            )
        ]
        activity = IngestionRunPresenter.current_activity_from_steps(steps, run_status=RUN_RUNNING)
        assert activity == {
            "kind": "published_module_merge",
            "stage": STAGE_CARD_DRAFT,
            "candidate_id": cand,
        }

    def test_candidate_merge_activity(self) -> None:
        steps = [
            _step(
                stage=STAGE_CANDIDATE_MERGE,
                input_summary={"activity": "candidate_merge"},
            )
        ]
        activity = IngestionRunPresenter.current_activity_from_steps(steps, run_status=RUN_RUNNING)
        assert activity == {
            "kind": "candidate_merge",
            "stage": STAGE_CANDIDATE_MERGE,
        }

    def test_none_when_run_not_running(self) -> None:
        steps = [_step(input_summary={"activity": "published_module_merge"})]
        assert IngestionRunPresenter.current_activity_from_steps(steps, run_status=RUN_SUCCEEDED) is None
