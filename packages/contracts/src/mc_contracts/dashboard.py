"""Dashboard view model contracts — platform → dashboard frontend."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from mc_contracts.localized import LocalizedString


class DigitalHelpModuleUsageItem(BaseModel):
    """One ranked module by combined digital_help_used + module_requested volume.

    Ranked by concrete ``module_id`` (not family) so demand/usage is never
    collapsed across module versions. Free-text ``module_requested`` events
    without a ``module_id`` are excluded.
    """

    module_id: UUID
    module_family_id: UUID | None = None
    digital_help_count: int
    module_requested_count: int
    title: LocalizedString | None = None


class DigitalHelpModuleUsageResponse(BaseModel):
    from_date: date
    to_date: date
    total_digital_help: int
    total_module_requested: int
    total_modules: int = 0
    limit: int
    offset: int
    modules: list[DigitalHelpModuleUsageItem] = Field(default_factory=list)


class TeamActivitySummary(BaseModel):
    total_users: int
    active_users: int
    non_active_users: int
    users_completed_module: int
    users_chatbot_engaged: int


class TeamMemberModuleActivity(BaseModel):
    module_id: UUID
    title: LocalizedString | None = None
    completed_in_range: bool
    completed_at: datetime | None = None


class TeamMemberChatbotModuleUsage(BaseModel):
    module_id: UUID
    title: LocalizedString | None = None
    query_count: int


class TeamActivityMemberDetail(BaseModel):
    """One current-level team-activity row (AM, PO, or SK).

    AM/PO metrics are rolled up from descendant SKs. ``can_drill_down`` is true
    for AM/PO rows and false for SK rows. AM/PO rows include SK-counted
    ``summary`` (same fields as the envelope); SK rows are ``null``.
    """

    user_id: int
    name: str
    role: str
    can_drill_down: bool
    is_active: bool
    is_chatbot_engaged: bool
    last_chat_at: datetime | None = None
    last_active_at: datetime | None = None
    has_completed_module_in_range: bool
    assigned_modules: list[TeamMemberModuleActivity] = Field(default_factory=list)
    chatbot_query_count: int = 0
    chatbot_unattributed_query_count: int = 0
    chatbot_modules: list[TeamMemberChatbotModuleUsage] = Field(default_factory=list)
    refreshers_generated: int = 0
    refreshers_completed: int = 0
    summary: TeamActivitySummary | None = None


class TeamActivityResponse(BaseModel):
    """One-level team activity report.

    Default focus is the caller (Admin/auth-off → AMs; AM → POs; PO → SKs).
    Optional ``user_id`` drills to a descendant's children. Optional ``depth``
    (query param, not echoed) selects a deeper member level under that focus.
    ``members`` is the current level only (no nesting). ``limit``/``offset``/
    ``total_pages`` page ``members``; ``total_users`` and ``summary.*`` always
    count Shastiya Kormi (SKs) under the effective focus. Drillable members
    (AM/PO) each include a nested SK-counted ``summary`` for that member's
    subtree; SK members have ``summary`` null. ``focus_user_id`` echoes the
    query param when set, otherwise null.
    """

    from_date: date
    to_date: date
    summary: TeamActivitySummary
    members: list[TeamActivityMemberDetail] = Field(default_factory=list)
    focus_user_id: int | None = None
    total_users: int
    total_members: int = 0
    total_pages: int
    limit: int
    offset: int
    server_time_utc: str


class TeamMemberQuestionItem(BaseModel):
    question: str
    occurrence_count: int
    last_asked_at: datetime


class TeamMemberQuestionsResponse(BaseModel):
    user_id: int
    from_date: date
    to_date: date
    questions: list[TeamMemberQuestionItem] = Field(default_factory=list)
    total_questions: int
    total_pages: int
    limit: int
    offset: int
    server_time_utc: str


class DashboardUserSummary(BaseModel):
    """Display fields for a CHW referenced by dashboard demand analytics."""

    user_id: int | None = None
    user_name: str | None = None
    user_role: str | None = None
    division: str | None = None
    district: str | None = None
    upazila: str | None = None


class DigitalHelpModuleQuestionItem(BaseModel):
    """One deduplicated chatbot question for a module with the latest asker."""

    question: str
    occurrence_count: int
    last_asked_at: datetime
    asked_by: DashboardUserSummary


class DigitalHelpModuleQuestionsResponse(BaseModel):
    """Paginated deduplicated chatbot questions for one module."""

    module_id: UUID
    title: LocalizedString | None = None
    from_date: date
    to_date: date
    questions: list[DigitalHelpModuleQuestionItem] = Field(default_factory=list)
    total_questions: int
    total_pages: int
    limit: int
    offset: int


class DigitalHelpModuleRequestItem(BaseModel):
    """One module_requested event for a concrete module."""

    requested_at: datetime
    reason: str | None = None
    requested_by: DashboardUserSummary


class DigitalHelpModuleRequestsResponse(BaseModel):
    """Paginated module_requested events for one concrete module_id."""

    module_id: UUID
    title: LocalizedString | None = None
    from_date: date
    to_date: date
    requests: list[DigitalHelpModuleRequestItem] = Field(default_factory=list)
    total_requests: int
    total_pages: int
    limit: int
    offset: int


class ModuleCreationSuggestionEvidenceItem(BaseModel):
    """One deduped chat question or free-text module request behind a suggestion."""

    source: str
    text: str
    occurrence_count: int
    last_seen_at: datetime | None = None
    prompted_by: DashboardUserSummary


class ModuleCreationSuggestionListItem(BaseModel):
    """One inferred module-creation suggestion for a UTC calendar day."""

    id: UUID
    suggestion_date: date
    suggestion_kind: str
    matched_module_id: UUID | None = None
    proposed_topic: str | None = None
    display_title: str
    rationale: str | None = None
    question_count: int
    request_count: int
    evidence_count: int
    rank: int
    computed_at: datetime


class ModuleCreationSuggestionListResponse(BaseModel):
    from_date: date
    to_date: date
    suggestions: list[ModuleCreationSuggestionListItem] = Field(default_factory=list)
    total_suggestions: int
    total_pages: int
    limit: int
    offset: int


class ModuleCreationSuggestionDetailResponse(BaseModel):
    suggestion: ModuleCreationSuggestionListItem
    questions: list[ModuleCreationSuggestionEvidenceItem] = Field(default_factory=list)
    requests: list[ModuleCreationSuggestionEvidenceItem] = Field(default_factory=list)


class ModuleDemandSummaryResponse(BaseModel):
    """Human-readable module demand summary for a dashboard date range."""

    from_date: date
    to_date: date
    summary: str


class PublishedModuleCompletionItem(BaseModel):
    """One published module version with scoped SK completion counts.

    Completions are counted per ``module_family_id`` (ledger grain). Multiple
    published versions of the same family in the date range each appear as a
    row but share the same ``completed_sk_count``.
    """

    module_id: UUID
    module_family_id: UUID
    title: LocalizedString | None = None
    published_at: datetime
    completed_sk_count: int
    total_descendant_sk_count: int


class PublishedModuleCompletionsResponse(BaseModel):
    """Modules published in range with Admin/AM descendant SK completion counts."""

    from_date: date
    to_date: date
    total_modules: int
    total_descendant_sk_count: int
    limit: int
    offset: int
    modules: list[PublishedModuleCompletionItem] = Field(default_factory=list)


class DocumentUsageTopItem(BaseModel):
    """One ranked document by view volume."""

    document_id: UUID
    document_title: str | None = None
    view_count: int


class DocumentUsageDocumentRow(BaseModel):
    """Per-document usage row."""

    document_id: UUID
    document_title: str | None = None
    total_views: int
    unique_users: int
    last_viewed_at: datetime | None = None
    last_viewed_by_user_id: int | None = None
    last_viewed_by_user_name: str | None = None


class DocumentUsageEventRow(BaseModel):
    """One document-view event for drill-down."""

    event_id: str
    document_id: UUID
    document_title: str | None = None
    user_id: int
    user_name: str | None = None
    user_role: str | None = None
    upazila_id: str | None = None
    district: str | None = None
    viewed_at: datetime | None = None


class DocumentUsageResponse(BaseModel):
    """Combined document-view analytics for PO / AM / Admin dashboards.

    One response carries KPIs, the per-document table, and event drill-down
    under the same filters.
    """

    from_date: date
    to_date: date
    total_views: int
    unique_documents: int
    unique_users: int
    top_documents: list[DocumentUsageTopItem] = Field(default_factory=list)
    total_document_rows: int = 0
    documents: list[DocumentUsageDocumentRow] = Field(default_factory=list)
    total_events: int = 0
    events: list[DocumentUsageEventRow] = Field(default_factory=list)
    documents_limit: int
    documents_offset: int
    events_limit: int
    events_offset: int
