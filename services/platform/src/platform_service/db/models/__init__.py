from platform_service.db.models.attribution_event import AttributionEvent
from platform_service.db.models.badge import Badge, BadgeModule
from platform_service.db.models.behavioural_gap import BehaviouralGap
from platform_service.db.models.chat_feedback_summary import ChatFeedbackSummary
from platform_service.db.models.chat_frequent_question import ChatFrequentQuestion
from platform_service.db.models.chw_badge import CHWBadge
from platform_service.db.models.chw_behavioural_gap_state import CHWBehaviouralGapState
from platform_service.db.models.chw_gap_telemetry_event import CHWGapTelemetryEvent
from platform_service.db.models.chw_learning_point_event import CHWLearningPointEvent
from platform_service.db.models.chw_module_completion import CHWModuleCompletion
from platform_service.db.models.chw_module_quiz_progress import CHWModuleQuizProgress
from platform_service.db.models.chw_quiz_question_state import CHWQuizQuestionState
from platform_service.db.models.chw_training_request import CHWTrainingRequest
from platform_service.db.models.config_threshold import ConfigThreshold
from platform_service.db.models.config_threshold_change import ConfigThresholdChange
from platform_service.db.models.content_block import ContentBlock
from platform_service.db.models.district import District
from platform_service.db.models.division import Division
from platform_service.db.models.document_assignment import DocumentAssignment
from platform_service.db.models.file_upload import FileUpload
from platform_service.db.models.hierarchy_user import HierarchyUser
from platform_service.db.models.ingest_batch import IngestBatch
from platform_service.db.models.ingestion_run import IngestionRun, IngestionRunStep
from platform_service.db.models.llm_call_cache import LlmCallCache
from platform_service.db.models.module import Module
from platform_service.db.models.module_assignment import ModuleAssignment
from platform_service.db.models.module_behavioural_gap import ModuleBehaviouralGap
from platform_service.db.models.module_candidate_draft import ModuleCandidateDraft
from platform_service.db.models.module_card import ModuleCard
from platform_service.db.models.module_creation_suggestion import (
    ModuleCreationSuggestion,
    ModuleCreationSuggestionEvidence,
)
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.models.module_lifecycle_event import ModuleLifecycleEvent
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
from platform_service.db.models.prompt_template import PromptTemplate
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.models.source_image import SourceImage
from platform_service.db.models.source_page import SourcePage
from platform_service.db.models.trigger_definition import ModuleTriggerBinding, TriggerDefinition
from platform_service.db.models.upazila import Upazila
from platform_service.db.models.user_upazila import UserUpazila

__all__ = [
    # audit
    "AttributionEvent",
    # source layer
    "ContentBlock",
    "FileUpload",
    "IngestBatch",
    "IngestionRun",
    "IngestionRunStep",
    "LlmCallCache",
    "ModuleCandidateDraft",
    "SourceDocument",
    "SourceImage",
    "SourcePage",
    # module layer
    # Cards live in ``module_card``; quiz questions stay relational for telemetry FKs.
    "Badge",
    "BadgeModule",
    "Module",
    "ModuleBehaviouralGap",
    "ModuleCreationSuggestion",
    "ModuleCreationSuggestionEvidence",
    "ModuleFamily",
    "ModuleLifecycleEvent",
    "ModuleCard",
    "ModuleQuizQuestion",
    "PromptTemplate",
    # gap + trigger layer (runtime delivery uses these; pipeline does not)
    "BehaviouralGap",
    "CHWBadge",
    "CHWBehaviouralGapState",
    "CHWGapTelemetryEvent",
    "CHWLearningPointEvent",
    "CHWModuleCompletion",
    "CHWModuleQuizProgress",
    "ModuleAssignment",
    "CHWQuizQuestionState",
    "DocumentAssignment",
    "CHWTrainingRequest",
    "ModuleTriggerBinding",
    "TriggerDefinition",
    # config
    "ChatFeedbackSummary",
    "ChatFrequentQuestion",
    "ConfigThreshold",
    "ConfigThresholdChange",
    # org hierarchy
    "Division",
    "District",
    "Upazila",
    "UserUpazila",
    "HierarchyUser",
]
