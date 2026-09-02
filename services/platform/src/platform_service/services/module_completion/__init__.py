"""Module completion event handlers — quiz progress, gap escalation, learning points, badges."""

from platform_service.services.module_completion.badge_award_handler import BadgeAwardHandler
from platform_service.services.module_completion.card_coverage import (
    card_coverage_count,
    is_module_card_coverage_complete,
)
from platform_service.services.module_completion.card_progress_handler import CardProgressHandler
from platform_service.services.module_completion.gap_escalation_handler import GapEscalationHandler
from platform_service.services.module_completion.learning_points_handler import LearningPointsHandler
from platform_service.services.module_completion.quiz_coverage import (
    is_module_quiz_coverage_complete,
    quiz_coverage_count,
)
from platform_service.services.module_completion.quiz_escalation_handler import QuizEscalationHandler
from platform_service.services.module_completion.quiz_progress_handler import QuizProgressHandler
from platform_service.services.module_completion.telemetry_parsing import (
    coerce_tenant_id,
    module_quiz_outcome_kind,
    parse_card_family_id,
    parse_card_id,
    parse_chw_id,
    parse_quiz_id,
    parse_quiz_score_pct,
    parse_uuid,
    spice_outcome_is_incorrect,
)

__all__ = [
    "BadgeAwardHandler",
    "CardProgressHandler",
    "GapEscalationHandler",
    "LearningPointsHandler",
    "QuizEscalationHandler",
    "QuizProgressHandler",
    "card_coverage_count",
    "coerce_tenant_id",
    "is_module_card_coverage_complete",
    "is_module_quiz_coverage_complete",
    "module_quiz_outcome_kind",
    "parse_card_family_id",
    "parse_card_id",
    "parse_chw_id",
    "parse_quiz_id",
    "parse_quiz_score_pct",
    "parse_uuid",
    "quiz_coverage_count",
    "spice_outcome_is_incorrect",
]
