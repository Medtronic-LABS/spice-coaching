"""Scenario sync service — builds ScenarioSyncBundle for device sync endpoint.

Devices (Android SDK) call /scenarios/sync?since_version=N to pull:
  - validated scenarios with version > N (excluding soft-deleted)
  - tombstone lists for removed scenarios / quizzes
  - associated validated quiz questions
  - ``current_version`` watermark for the next sync cursor
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from mc_contracts.sync import (
    BehaviouralGapSyncPayload,
    CHWBehaviouralGapStateSyncPayload,
    CHWModuleCompletionSyncPayload,
    ConfigSyncBundle,
    GapsSyncBundle,
    ModuleFamilySyncPayload,
    ModuleQuizQuestionPayload,
    ModulesSyncBundle,
    ModuleSyncPayload,
    ModuleTriggerBindingSyncPayload,
    TriggerDefinitionSyncPayload,
    TriggersSyncBundle,
)
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.behavioural_gap import BehaviouralGap
from platform_service.db.models.chw_behavioural_gap_state import CHWBehaviouralGapState
from platform_service.db.models.chw_module_completion import CHWModuleCompletion
from platform_service.db.models.config_threshold import ConfigThreshold
from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
from platform_service.db.models.trigger_definition import ModuleTriggerBinding, TriggerDefinition
from platform_service.services.learning_points_service import LearningPointsService

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_config_bundle(self) -> ConfigSyncBundle:
        """Return current snapshot of all config thresholds."""
        stmt = select(ConfigThreshold)
        rows = list((await self._session.execute(stmt)).scalars().all())
        thresholds = {row.key: row.value_json for row in rows}
        return ConfigSyncBundle(
            thresholds=thresholds,
            server_time_utc=datetime.now(UTC).isoformat(),
        )

    async def get_modules_bundle(self, *, since: datetime) -> ModulesSyncBundle:
        families_stmt = (
            select(ModuleFamily)
            .where(ModuleFamily.created_at > since)
            .order_by(ModuleFamily.created_at.asc(), ModuleFamily.id.asc())
        )
        families = list((await self._session.execute(families_stmt)).scalars().all())

        stmt = (
            select(Module)
            .where(Module.lifecycle_status == "published", Module.updated_at > since)
            .order_by(Module.updated_at.asc(), Module.id.asc())
        )
        modules = list((await self._session.execute(stmt)).scalars().all())

        quiz_by_module_id: dict = {}
        module_ids = [m.id for m in modules]
        if module_ids:
            quiz_stmt = (
                select(ModuleQuizQuestion)
                .where(ModuleQuizQuestion.module_id.in_(module_ids))
                .order_by(
                    ModuleQuizQuestion.module_id.asc(),
                    ModuleQuizQuestion.question_order.asc().nullslast(),
                    ModuleQuizQuestion.id.asc(),
                )
            )
            quiz_rows = list((await self._session.execute(quiz_stmt)).scalars().all())
            for row in quiz_rows:
                if row.module_id is None:
                    continue
                quiz_by_module_id.setdefault(row.module_id, []).append(
                    ModuleQuizQuestionPayload(
                        id=row.id,
                        question_order=row.question_order,
                        question_bn=row.question_bn,
                        question_en=row.question_en,
                        case_setup_bn=row.case_setup_bn,
                        case_setup_en=row.case_setup_en,
                        options_bn=list(row.options_bn or []),
                        options_en=list(row.options_en) if row.options_en else None,
                        correct_indices=list(row.correct_indices or []),
                        explanation_bn=row.explanation_bn,
                        explanation_en=row.explanation_en,
                        difficulty=row.difficulty,
                    )
                )

        payloads = []
        for m in modules:
            cards = list((m.module_json or {}).get("cards", []))
            payloads.append(
                ModuleSyncPayload(
                    id=m.id,
                    module_family_id=m.module_family_id,
                    version=m.version,
                    title_bn=m.title_bn,
                    title_en=m.title_en,
                    description_bn=m.description_bn,
                    description_en=m.description_en,
                    domain=m.domain,
                    sub_domain=m.sub_domain,
                    module_type=m.module_type,
                    tenant_id=m.tenant_id,
                    estimated_minutes=m.estimated_minutes,
                    difficulty_level=m.difficulty_level,
                    pass_threshold_override=m.pass_threshold_override,
                    clinically_reviewed=m.clinically_reviewed,
                    published_at=m.published_at,
                    updated_at=m.updated_at,
                    cards=cards,
                    quiz=list(quiz_by_module_id.get(m.id, [])),
                )
            )

        return ModulesSyncBundle(
            modules=payloads,
            module_families=[
                ModuleFamilySyncPayload(
                    id=f.id,
                    module_code=f.module_code,
                    created_at=f.created_at,
                    created_by=f.created_by,
                    current_published_module_id=f.current_published_module_id,
                )
                for f in families
            ],
            server_time_utc=datetime.now(UTC).isoformat(),
        )

    async def get_triggers_bundle(self, *, since: datetime) -> TriggersSyncBundle:
        triggers_stmt = (
            select(TriggerDefinition)
            .where(
                TriggerDefinition.status == "active",
                TriggerDefinition.updated_at > since,
            )
            .order_by(TriggerDefinition.updated_at.asc(), TriggerDefinition.id.asc())
        )
        triggers = list((await self._session.execute(triggers_stmt)).scalars().all())

        trigger_ids = [t.id for t in triggers]
        bindings: list[ModuleTriggerBinding] = []
        if trigger_ids:
            bindings_stmt = (
                select(ModuleTriggerBinding)
                .where(ModuleTriggerBinding.trigger_definition_id.in_(trigger_ids))
                .order_by(
                    ModuleTriggerBinding.trigger_definition_id.asc(),
                    ModuleTriggerBinding.priority_weight.desc(),
                    ModuleTriggerBinding.id.asc(),
                )
            )
            bindings = list((await self._session.execute(bindings_stmt)).scalars().all())

        return TriggersSyncBundle(
            triggers=[
                TriggerDefinitionSyncPayload(
                    id=t.id,
                    trigger_kind=t.trigger_kind,
                    trigger_code=t.trigger_code,
                    description=t.description,
                    predicate_jsonb=dict(t.predicate_jsonb or {}),
                    predicate_schema_version=t.predicate_schema_version,
                    status=t.status,
                    tenant_id=t.tenant_id,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                )
                for t in triggers
            ],
            bindings=[
                ModuleTriggerBindingSyncPayload(
                    id=b.id,
                    trigger_definition_id=b.trigger_definition_id,
                    module_family_id=b.module_family_id,
                    relationship=b.relationship,
                    priority_weight=b.priority_weight,
                    notes=b.notes,
                )
                for b in bindings
            ],
            server_time_utc=datetime.now(UTC).isoformat(),
        )

    async def get_gaps_bundle(self, *, since: datetime | None, chw_id: int | None) -> GapsSyncBundle:
        gaps_stmt = select(BehaviouralGap).where(BehaviouralGap.status == "active")
        if since is not None:
            gaps_stmt = gaps_stmt.where(BehaviouralGap.updated_at > since)
        gaps_stmt = gaps_stmt.order_by(BehaviouralGap.updated_at.asc(), BehaviouralGap.id.asc())
        gaps = list((await self._session.execute(gaps_stmt)).scalars().all())

        gap_payloads = [
            BehaviouralGapSyncPayload(
                id=g.id,
                gap_code=g.gap_code,
                description=g.description,
                domain=g.domain,
                severity_default=g.severity_default,
                detection_rule_jsonb=dict(g.detection_rule_jsonb or {}),
                updated_at=g.updated_at,
            )
            for g in gaps
        ]

        if chw_id is None:
            return GapsSyncBundle(
                behavioural_gaps=gap_payloads,
                chw_behavioural_gap_states=[],
                chw_module_completions=[],
                server_time_utc=datetime.now(UTC).isoformat(),
                total_points=0,
            )

        states_stmt = select(CHWBehaviouralGapState).where(CHWBehaviouralGapState.chw_id == chw_id)
        if since is not None:
            states_stmt = states_stmt.where(
                CHWBehaviouralGapState.updated_at.is_not(None),
                CHWBehaviouralGapState.updated_at > since,
            )
        states_stmt = states_stmt.order_by(
            CHWBehaviouralGapState.updated_at.asc().nullslast(),
            CHWBehaviouralGapState.behavioural_gap_id.asc(),
        )
        states = list((await self._session.execute(states_stmt)).scalars().all())

        state_payloads = [
            CHWBehaviouralGapStateSyncPayload(
                chw_id=s.chw_id,
                behavioural_gap_id=s.behavioural_gap_id,
                tenant_id=s.tenant_id,
                severity_current=s.severity_current,
                first_observed_at=s.first_observed_at,
                last_observed_at=s.last_observed_at,
                last_reinforced_at=s.last_reinforced_at,
                occurrence_count=s.occurrence_count,
                failed_attempts_count=s.failed_attempts_count,
                last_failed_attempt_at=s.last_failed_attempt_at,
                escalated_to_supervisor=s.escalated_to_supervisor,
                status=s.status,
                updated_at=s.updated_at,
            )
            for s in states
        ]

        comps_stmt = select(CHWModuleCompletion).where(CHWModuleCompletion.chw_id == chw_id)
        if since is not None:
            comps_stmt = comps_stmt.where(
                or_(
                    CHWModuleCompletion.latest_attempt_at > since,
                    CHWModuleCompletion.completed_at > since,
                    CHWModuleCompletion.reinforcement_due_at > since,
                )
            )
        comps_stmt = comps_stmt.order_by(CHWModuleCompletion.module_family_id.asc())
        comps = list((await self._session.execute(comps_stmt)).scalars().all())

        comp_payloads = [
            CHWModuleCompletionSyncPayload(
                chw_id=c.chw_id,
                module_family_id=c.module_family_id,
                latest_completed_module_id=c.latest_completed_module_id,
                latest_attempt_module_id=c.latest_attempt_module_id,
                completed_at=c.completed_at,
                latest_attempt_at=c.latest_attempt_at,
                latest_quiz_score=c.latest_quiz_score,
                latest_attempt_passed=c.latest_attempt_passed,
                attempts_since_last_pass=c.attempts_since_last_pass,
                reinforcement_due_at=c.reinforcement_due_at,
                tenant_id=c.tenant_id,
            )
            for c in comps
        ]

        total_pts = await LearningPointsService(self._session).get_total_points(chw_id=chw_id)

        return GapsSyncBundle(
            behavioural_gaps=gap_payloads,
            chw_behavioural_gap_states=state_payloads,
            chw_module_completions=comp_payloads,
            server_time_utc=datetime.now(UTC).isoformat(),
            total_points=total_pts,
        )
