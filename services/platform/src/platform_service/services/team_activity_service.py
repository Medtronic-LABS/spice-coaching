"""Team activity dashboard — hierarchy-scoped engagement and completion reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from mc_contracts.dashboard import (
    TeamActivityMemberDetail,
    TeamActivityResponse,
    TeamActivitySummary,
    TeamMemberChatbotModuleUsage,
    TeamMemberModuleActivity,
    TeamMemberQuestionItem,
    TeamMemberQuestionsResponse,
)
from mc_contracts.enums import HierarchyRole, Outcome
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_identity import TeamActivityScope
from platform_service.clickhouse.client import ClickHouseClient
from platform_service.clickhouse.question_sql import QUESTION_EXTRACT_SQL, QUESTION_NORMALIZE_KEY_SQL
from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.repositories.module_assignment_repository import ModuleAssignmentRepository
from platform_service.db.repositories.module_completion_repository import ModuleCompletionRepository
from platform_service.db.repositories.module_repository import ModuleRepository
from platform_service.services.dashboard_hierarchy import (
    OrgUser,
    descendants_with_role,
    direct_children,
    filter_users_by_chw_ids,
    is_team_activity_descendant,
    member_role_at_depth,
    org_user_index,
    sks_under_focus,
    sks_under_member,
)

_DIGITAL_HELP_EVENT = "digital_help_used"
_REFRESHER_MISS_OUTCOMES = frozenset({Outcome.WRONG.value, Outcome.INCORRECT.value})

TEAM_ACTIVITY_SORT_KEYS = frozenset({"name", "chatbot_engagement", "module_completion", "performance_status"})
TEAM_ACTIVITY_SORT_DIRS = frozenset({"asc", "desc"})
DEFAULT_TEAM_ACTIVITY_SORT_BY = "name"
DEFAULT_TEAM_ACTIVITY_SORT_DIR = "asc"
PERFORMANCE_THRESHOLD = 0.60
PERFORMANCE_STATUS_ON_TRACK = "on_track"
PERFORMANCE_STATUS_AT_RISK = "at_risk"


@dataclass(frozen=True, slots=True)
class _SkSortFlags:
    is_active: bool
    is_chatbot_engaged: bool
    has_completed_module_in_range: bool
    completed_all_assigned_in_range: bool


@dataclass(slots=True)
class _SkMetricsCache:
    summary: TeamActivitySummary
    flags_by_chw: dict[int, _SkSortFlags]
    completions_by_chw: dict[int, dict[UUID, datetime]]
    assigned_by_chw: dict[int, set[UUID]]
    sk_on_track: dict[int, bool]
    name_by_id: dict[int, str]


def _completed_all_assigned(assigned: set[UUID], completed: set[UUID]) -> bool:
    """True when the SK has at least one assignment and completed every assigned module."""
    return bool(assigned) and assigned <= completed


def _sk_completed_all_assigned_modules(sk: TeamActivityMemberDetail) -> bool:
    return bool(sk.assigned_modules) and all(mod.completed_in_range for mod in sk.assigned_modules)


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    return None


def _date_to_datetime_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _to_datetime(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    return None


def _utc_range_bounds(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    from_ts = datetime.combine(from_date, time.min, tzinfo=UTC)
    to_ts = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC) - timedelta(microseconds=1)
    return from_ts, to_ts


def _count_refreshers(
    events: list[dict[str, Any]],
) -> dict[int, dict[str, int]]:
    """Fold ordered quiz attempts into refresher generated/completed counts.

    Events must already be ordered by ``(chw_id, timestamp_utc ASC, id ASC)``.
    Per ``(chw_id, quiz_id)``: first miss (``incorrect`` or ``wrong``) opens a
    refresher; subsequent miss of either while open is a no-op; ``correct``
    while open closes it.
    """
    out: dict[int, dict[str, int]] = {}
    open_by_chw: dict[int, set[UUID]] = {}

    for event in events:
        chw_id = _to_int(event.get("chw_id"), default=-1)
        if chw_id < 0:
            continue
        quiz_id = _to_uuid(event.get("quiz_id"))
        outcome = event.get("outcome")
        if quiz_id is None or outcome is None:
            continue
        outcome_str = str(outcome).strip().lower()
        if not outcome_str:
            continue

        bucket = out.setdefault(chw_id, {"generated": 0, "completed": 0})
        open_quizzes = open_by_chw.setdefault(chw_id, set())

        if outcome_str in _REFRESHER_MISS_OUTCOMES:
            if quiz_id not in open_quizzes:
                open_quizzes.add(quiz_id)
                bucket["generated"] += 1
        elif outcome_str == "correct":
            if quiz_id in open_quizzes:
                open_quizzes.remove(quiz_id)
                bucket["completed"] += 1

    return out


def _max_datetime(*values: datetime | None) -> datetime | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return max(present)


def _child_share_on_track(on_track_count: int, total: int) -> bool:
    if total <= 0:
        return False
    return (on_track_count / total) > PERFORMANCE_THRESHOLD


def _sk_module_on_track(
    assigned_module_ids: set[UUID],
    responsive_module_ids: set[UUID],
) -> bool:
    if not assigned_module_ids:
        return False
    responsive_count = sum(1 for module_id in assigned_module_ids if module_id in responsive_module_ids)
    return (responsive_count / len(assigned_module_ids)) >= PERFORMANCE_THRESHOLD


def _build_performance_status_by_user_id(
    by_id: dict[int, OrgUser],
    *,
    sk_on_track: dict[int, bool],
    geo_chw_ids: frozenset[int] | None,
) -> dict[int, str]:
    """Map hierarchy user ids to ``on_track`` / ``at_risk`` using the 60% cascade."""
    po_role = HierarchyRole.PO.value
    am_role = HierarchyRole.AREA_MANAGER.value
    sk_role = HierarchyRole.SHASTIYA_KORMI.value

    status_by_id: dict[int, str] = {}
    po_on_track: dict[int, bool] = {}

    for user in by_id.values():
        if user.role == sk_role:
            on_track = sk_on_track.get(user.id, False)
            status_by_id[user.id] = PERFORMANCE_STATUS_ON_TRACK if on_track else PERFORMANCE_STATUS_AT_RISK

    for user in by_id.values():
        if user.role != po_role:
            continue
        sk_ids = [sk.id for sk in filter_users_by_chw_ids(sks_under_member(by_id, user), geo_chw_ids)]
        on_track_count = sum(1 for sk_id in sk_ids if sk_on_track.get(sk_id, False))
        po_on_track[user.id] = _child_share_on_track(on_track_count, len(sk_ids))
        status_by_id[user.id] = (
            PERFORMANCE_STATUS_ON_TRACK if po_on_track[user.id] else PERFORMANCE_STATUS_AT_RISK
        )

    for user in by_id.values():
        if user.role != am_role:
            continue
        po_children = direct_children(by_id, user.id, po_role)
        if not po_children:
            status_by_id[user.id] = PERFORMANCE_STATUS_AT_RISK
            continue
        on_track_count = sum(1 for po in po_children if po_on_track.get(po.id, False))
        on_track = _child_share_on_track(on_track_count, len(po_children))
        status_by_id[user.id] = PERFORMANCE_STATUS_ON_TRACK if on_track else PERFORMANCE_STATUS_AT_RISK

    return status_by_id


def _performance_status_for_user(
    user_id: int,
    status_by_id: dict[int, str],
) -> str:
    return status_by_id.get(user_id, PERFORMANCE_STATUS_AT_RISK)


def _summary_from_sk_details(sk_details: list[TeamActivityMemberDetail]) -> TeamActivitySummary:
    """SK-counted summary for one drillable member (same fields as the envelope)."""
    total_users = len(sk_details)
    active_users = sum(1 for sk in sk_details if sk.is_active)
    return TeamActivitySummary(
        total_users=total_users,
        active_users=active_users,
        non_active_users=total_users - active_users,
        users_completed_module=sum(1 for sk in sk_details if _sk_completed_all_assigned_modules(sk)),
        users_chatbot_engaged=sum(1 for sk in sk_details if sk.is_chatbot_engaged),
    )


def _sk_sort_flags(chw_id: int, flags_by_chw: dict[int, _SkSortFlags]) -> _SkSortFlags:
    return flags_by_chw.get(
        chw_id,
        _SkSortFlags(
            is_active=False,
            is_chatbot_engaged=False,
            has_completed_module_in_range=False,
            completed_all_assigned_in_range=False,
        ),
    )


def _rollup_sort_counts(
    sk_ids: list[int],
    flags_by_chw: dict[int, _SkSortFlags],
) -> tuple[int, int, int]:
    """Return (non_active_users, users_chatbot_engaged, users_completed_module).

    ``users_completed_module`` matches envelope/summary semantics (all in-window
    assigned modules completed). SK row ``sort_by=module_completion`` still uses
    ``has_completed_module_in_range`` (any completion).
    """
    non_active = 0
    chatbot = 0
    completed = 0
    for sk_id in sk_ids:
        flags = _sk_sort_flags(sk_id, flags_by_chw)
        if not flags.is_active:
            non_active += 1
        if flags.is_chatbot_engaged:
            chatbot += 1
        if flags.completed_all_assigned_in_range:
            completed += 1
    return non_active, chatbot, completed


def _member_sort_primary(
    member: OrgUser,
    *,
    member_role: str | None,
    flags_by_chw: dict[int, _SkSortFlags],
    sks_by_member: dict[int, list[int]],
    performance_status_by_id: dict[int, str],
    sort_by: str,
) -> int:
    """Numeric primary key: smaller comes first for product-natural (sort_dir=asc) order."""
    if sort_by == "performance_status":
        return (
            0
            if _performance_status_for_user(member.id, performance_status_by_id) == PERFORMANCE_STATUS_AT_RISK
            else 1
        )

    if member_role == HierarchyRole.SHASTIYA_KORMI.value:
        flags = _sk_sort_flags(member.id, flags_by_chw)
        if sort_by == "chatbot_engagement":
            return 0 if not flags.is_chatbot_engaged else 1
        if sort_by == "module_completion":
            return 0 if not flags.has_completed_module_in_range else 1
        return 0

    non_active, chatbot, completed = _rollup_sort_counts(
        sks_by_member.get(member.id, []),
        flags_by_chw,
    )
    if sort_by == "chatbot_engagement":
        return chatbot
    if sort_by == "module_completion":
        return completed
    return 0


def _filter_team_activity_children_by_name(
    children: list[OrgUser],
    name_query: str | None,
) -> list[OrgUser]:
    if not name_query:
        return children
    needle = name_query.casefold()
    return [member for member in children if needle in member.name.casefold()]


def _sort_team_activity_children(
    children: list[OrgUser],
    *,
    member_role: str | None,
    flags_by_chw: dict[int, _SkSortFlags],
    sks_by_member: dict[int, list[int]],
    performance_status_by_id: dict[int, str],
    sort_by: str,
    sort_dir: str,
) -> list[OrgUser]:
    if not children:
        return children
    if sort_by == "name":
        ordered = sorted(children, key=lambda u: u.id)
        ordered.sort(key=lambda u: u.name, reverse=sort_dir == "desc")
        return ordered

    direction = -1 if sort_dir == "desc" else 1

    def key(member: OrgUser) -> tuple[int, str, int]:
        primary = _member_sort_primary(
            member,
            member_role=member_role,
            flags_by_chw=flags_by_chw,
            sks_by_member=sks_by_member,
            performance_status_by_id=performance_status_by_id,
            sort_by=sort_by,
        )
        return (direction * primary, member.name, member.id)

    return sorted(children, key=key)


def _aggregate_member_from_sks(
    *,
    user_id: int,
    name: str,
    role: str,
    sk_details: list[TeamActivityMemberDetail],
    performance_status: str,
) -> TeamActivityMemberDetail:
    """Roll AM/PO activity metrics up from descendant SK details (no self events)."""
    can_drill_down = role != HierarchyRole.SHASTIYA_KORMI.value
    member_summary = _summary_from_sk_details(sk_details)
    if not sk_details:
        return TeamActivityMemberDetail(
            user_id=user_id,
            name=name,
            role=role,
            can_drill_down=can_drill_down,
            is_active=False,
            is_chatbot_engaged=False,
            last_chat_at=None,
            last_active_at=None,
            has_completed_module_in_range=False,
            assigned_modules=[],
            chatbot_query_count=0,
            chatbot_unattributed_query_count=0,
            chatbot_modules=[],
            refreshers_generated=0,
            refreshers_completed=0,
            performance_status=performance_status,
            summary=member_summary,
        )

    assigned_by_id: dict[UUID, TeamMemberModuleActivity] = {}
    for sk in sk_details:
        for mod in sk.assigned_modules:
            existing = assigned_by_id.get(mod.module_id)
            if existing is None:
                assigned_by_id[mod.module_id] = TeamMemberModuleActivity(
                    module_id=mod.module_id,
                    title=mod.title,
                    completed_in_range=mod.completed_in_range,
                    completed_at=mod.completed_at,
                )
                continue
            completed_in_range = existing.completed_in_range or mod.completed_in_range
            completed_at = _max_datetime(existing.completed_at, mod.completed_at)
            assigned_by_id[mod.module_id] = TeamMemberModuleActivity(
                module_id=mod.module_id,
                title=existing.title if existing.title is not None else mod.title,
                completed_in_range=completed_in_range,
                completed_at=completed_at,
            )

    chatbot_by_id: dict[UUID, TeamMemberChatbotModuleUsage] = {}
    for sk in sk_details:
        for usage in sk.chatbot_modules:
            existing = chatbot_by_id.get(usage.module_id)
            if existing is None:
                chatbot_by_id[usage.module_id] = TeamMemberChatbotModuleUsage(
                    module_id=usage.module_id,
                    title=usage.title,
                    query_count=usage.query_count,
                )
            else:
                chatbot_by_id[usage.module_id] = TeamMemberChatbotModuleUsage(
                    module_id=usage.module_id,
                    title=existing.title if existing.title is not None else usage.title,
                    query_count=existing.query_count + usage.query_count,
                )

    return TeamActivityMemberDetail(
        user_id=user_id,
        name=name,
        role=role,
        can_drill_down=can_drill_down,
        is_active=any(sk.is_active for sk in sk_details),
        is_chatbot_engaged=any(sk.is_chatbot_engaged for sk in sk_details),
        last_chat_at=_max_datetime(*(sk.last_chat_at for sk in sk_details)),
        last_active_at=_max_datetime(*(sk.last_active_at for sk in sk_details)),
        has_completed_module_in_range=any(sk.has_completed_module_in_range for sk in sk_details),
        assigned_modules=sorted(assigned_by_id.values(), key=lambda m: str(m.module_id)),
        chatbot_query_count=sum(sk.chatbot_query_count for sk in sk_details),
        chatbot_unattributed_query_count=sum(sk.chatbot_unattributed_query_count for sk in sk_details),
        chatbot_modules=sorted(
            chatbot_by_id.values(),
            key=lambda item: (-item.query_count, str(item.module_id)),
        ),
        refreshers_generated=sum(sk.refreshers_generated for sk in sk_details),
        refreshers_completed=sum(sk.refreshers_completed for sk in sk_details),
        performance_status=performance_status,
        summary=member_summary,
    )


class TeamActivityService:
    def __init__(
        self,
        ch_client: ClickHouseClient,
        session: AsyncSession,
    ) -> None:
        self._ch = ch_client
        self._session = session

    async def get_team_activity(
        self,
        *,
        scope: TeamActivityScope,
        focus_user_id: int | None,
        from_date: date,
        to_date: date,
        limit: int,
        offset: int,
        tenant_id: int | None,
        depth: int = 0,
        geo_chw_ids: frozenset[int] | None = None,
        sort_by: str = DEFAULT_TEAM_ACTIVITY_SORT_BY,
        sort_dir: str = DEFAULT_TEAM_ACTIVITY_SORT_DIR,
        name_query: str | None = None,
    ) -> TeamActivityResponse:
        hierarchy_tenant = tenant_id if tenant_id is not None else DEFAULT_TENANT_ID
        by_id = await org_user_index(self._session, tenant_id=hierarchy_tenant)

        focus_id, focus_role = self._resolve_focus(
            by_id,
            scope=scope,
            focus_user_id=focus_user_id,
        )
        member_role = member_role_at_depth(focus_role, depth)
        if member_role is None and not (focus_role == HierarchyRole.SHASTIYA_KORMI.value and depth == 0):
            # depth=0 on SK focus → empty members (valid). Any other miss → illegal depth.
            raise AppError(
                ErrorCode.VALIDATION_ERROR.value,
                f"depth={depth} is not valid for the effective focus role",
                status=422,
            )
        children = (
            []
            if member_role is None
            else list(descendants_with_role(by_id, focus_id, focus_role, member_role))
        )

        all_sks = filter_users_by_chw_ids(
            sks_under_focus(by_id, focus_id, focus_role),
            geo_chw_ids,
        )
        all_sk_members = [{"id": u.id, "name": u.name} for u in sorted(all_sks, key=lambda u: u.name)]
        all_chw_ids = [int(m["id"]) for m in all_sk_members]

        metrics = await self._load_sk_metrics(
            members=all_sk_members,
            all_chw_ids=all_chw_ids,
            from_date=from_date,
            to_date=to_date,
            tenant_id=tenant_id,
            hierarchy_tenant=hierarchy_tenant,
        )
        performance_status_by_id = _build_performance_status_by_user_id(
            by_id,
            sk_on_track=metrics.sk_on_track,
            geo_chw_ids=geo_chw_ids,
        )

        sks_by_member: dict[int, list[int]] = {}
        if member_role is not None and member_role != HierarchyRole.SHASTIYA_KORMI.value:
            for member in children:
                member_sks = filter_users_by_chw_ids(
                    sks_under_member(by_id, member),
                    geo_chw_ids,
                )
                sks_by_member[member.id] = [u.id for u in member_sks]

        children = _filter_team_activity_children_by_name(children, name_query)
        children = _sort_team_activity_children(
            children,
            member_role=member_role,
            flags_by_chw=metrics.flags_by_chw,
            sks_by_member=sks_by_member,
            performance_status_by_id=performance_status_by_id,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        total_members = len(children)
        total_pages = (total_members + limit - 1) // limit if total_members > 0 else 0
        paged_children = children[offset : offset + limit]

        detail_chw_ids: list[int] = []
        if member_role == HierarchyRole.SHASTIYA_KORMI.value:
            detail_chw_ids = [u.id for u in filter_users_by_chw_ids(list(paged_children), geo_chw_ids)]
        elif member_role is not None:
            for member in paged_children:
                detail_chw_ids.extend(sks_by_member.get(member.id, []))

        details_by_id = await self._build_sk_details(
            metrics=metrics,
            detail_chw_ids=detail_chw_ids,
            from_date=from_date,
            to_date=to_date,
            tenant_id=tenant_id,
        )

        members: list[TeamActivityMemberDetail]
        if member_role == HierarchyRole.SHASTIYA_KORMI.value:
            members = [details_by_id[u.id] for u in paged_children if u.id in details_by_id]
        elif member_role is None:
            members = []
        else:
            members = [
                _aggregate_member_from_sks(
                    user_id=member.id,
                    name=member.name,
                    role=member.role,
                    sk_details=[
                        details_by_id[sk_id]
                        for sk_id in sks_by_member.get(member.id, [])
                        if sk_id in details_by_id
                    ],
                    performance_status=_performance_status_for_user(
                        member.id,
                        performance_status_by_id,
                    ),
                )
                for member in paged_children
            ]

        return TeamActivityResponse(
            from_date=from_date,
            to_date=to_date,
            summary=metrics.summary,
            members=members,
            focus_user_id=focus_user_id,
            total_users=len(all_sk_members),
            total_members=total_members,
            total_pages=total_pages,
            limit=limit,
            offset=offset,
            server_time_utc=datetime.now(UTC).isoformat(),
        )

    @staticmethod
    def _resolve_focus(
        by_id: dict[int, OrgUser],
        *,
        scope: TeamActivityScope,
        focus_user_id: int | None,
    ) -> tuple[int | None, str | None]:
        """Return (effective_focus_id, focus_role). Synthetic Admin root → (None, None)."""
        if focus_user_id is not None:
            if not is_team_activity_descendant(
                by_id,
                scope.viewer_id,
                focus_user_id,
                unrestricted=scope.unrestricted,
            ):
                raise AppError(
                    ErrorCode.FORBIDDEN.value,
                    "user_id is outside the caller's team hierarchy",
                    status=403,
                )
            focus = by_id[focus_user_id]
            return focus.id, focus.role

        if scope.unrestricted:
            return None, None

        if scope.viewer_id is None:
            raise AppError(ErrorCode.FORBIDDEN.value, "authenticated user has no id", status=403)

        viewer = by_id.get(scope.viewer_id)
        if viewer is None:
            raise AppError(
                ErrorCode.FORBIDDEN.value,
                "caller is not present in the tenant hierarchy",
                status=403,
            )
        return viewer.id, viewer.role

    async def _load_sk_metrics(
        self,
        *,
        members: list[dict[str, Any]],
        all_chw_ids: list[int],
        from_date: date,
        to_date: date,
        tenant_id: int | None,
        hierarchy_tenant: int,
    ) -> _SkMetricsCache:
        """Envelope SK summary plus per-SK sort flags for every member."""
        from_ts, to_ts = _utc_range_bounds(from_date, to_date)
        total_users = len(members)

        daily_by_chw = await self._fetch_daily_summary(
            chw_ids=all_chw_ids,
            from_date=from_date,
            to_date=to_date,
            tenant_id=tenant_id,
        )
        completions = await ModuleCompletionRepository(self._session).list_completed_in_range_for_chws(
            chw_ids=all_chw_ids,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        completions_by_chw: dict[int, dict[UUID, datetime]] = {}
        for comp in completions:
            if comp.completed_at is None or comp.latest_completed_module_id is None:
                continue
            completions_by_chw.setdefault(comp.chw_id, {})[comp.latest_completed_module_id] = (
                comp.completed_at
            )

        assigned_by_chw = await ModuleAssignmentRepository(
            self._session
        ).list_module_ids_assigned_in_range_for_chws(
            chw_ids=all_chw_ids,
            tenant_id=hierarchy_tenant,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        for member in members:
            assigned_by_chw.setdefault(int(member["id"]), set())

        responsive_by_chw = await self._fetch_responsive_module_ids(
            chw_ids=all_chw_ids,
            from_date=from_date,
            to_date=to_date,
            tenant_id=tenant_id,
        )

        flags_by_chw: dict[int, _SkSortFlags] = {}
        sk_on_track: dict[int, bool] = {}
        active_users = 0
        users_chatbot_engaged = 0
        users_completed_module = 0
        for member in members:
            chw_id = int(member["id"])
            daily = daily_by_chw.get(chw_id, {})
            is_active = bool(daily.get("is_active"))
            is_chatbot_engaged = bool(daily.get("is_chatbot_engaged"))
            assigned_module_ids = assigned_by_chw.get(chw_id, set())
            member_completions = completions_by_chw.get(chw_id, {})
            completed_module_ids = set(member_completions.keys())
            has_completed = bool(assigned_module_ids & completed_module_ids)
            completed_all = _completed_all_assigned(assigned_module_ids, completed_module_ids)
            responsive_module_ids = responsive_by_chw.get(chw_id, set())
            sk_on_track[chw_id] = _sk_module_on_track(assigned_module_ids, responsive_module_ids)
            flags_by_chw[chw_id] = _SkSortFlags(
                is_active=is_active,
                is_chatbot_engaged=is_chatbot_engaged,
                has_completed_module_in_range=has_completed,
                completed_all_assigned_in_range=completed_all,
            )
            if is_active:
                active_users += 1
            if is_chatbot_engaged:
                users_chatbot_engaged += 1
            if completed_all:
                users_completed_module += 1

        summary = TeamActivitySummary(
            total_users=total_users,
            active_users=active_users,
            non_active_users=total_users - active_users,
            users_completed_module=users_completed_module,
            users_chatbot_engaged=users_chatbot_engaged,
        )
        return _SkMetricsCache(
            summary=summary,
            flags_by_chw=flags_by_chw,
            completions_by_chw=completions_by_chw,
            assigned_by_chw=assigned_by_chw,
            sk_on_track=sk_on_track,
            name_by_id={int(m["id"]): str(m["name"]) for m in members},
        )

    async def _build_sk_details(
        self,
        *,
        metrics: _SkMetricsCache,
        detail_chw_ids: list[int],
        from_date: date,
        to_date: date,
        tenant_id: int | None,
    ) -> dict[int, TeamActivityMemberDetail]:
        """Full detail rows for paged SK ids, reusing envelope metric caches."""
        if not detail_chw_ids:
            return {}

        chatbot_by_chw = await self._fetch_digital_help(
            chw_ids=detail_chw_ids,
            from_date=from_date,
            to_date=to_date,
            tenant_id=tenant_id,
        )
        last_activity_by_chw = await self._fetch_last_activity_timestamps(
            chw_ids=detail_chw_ids,
            tenant_id=tenant_id,
        )
        quiz_attempts = await self._fetch_quiz_attempts(
            chw_ids=detail_chw_ids,
            from_date=from_date,
            to_date=to_date,
            tenant_id=tenant_id,
        )
        refreshers_by_chw = _count_refreshers(quiz_attempts)

        all_module_ids: set[UUID] = set()
        for chw_id in detail_chw_ids:
            all_module_ids.update(metrics.assigned_by_chw.get(chw_id, set()))
            for module_id, _count in chatbot_by_chw.get(chw_id, {}).get("by_module", {}).items():
                if module_id is not None:
                    all_module_ids.add(module_id)

        title_by_module: dict[UUID, Any] = {}
        if all_module_ids:
            modules = await ModuleRepository(self._session).list_modules_by_ids(
                list(all_module_ids),
                tenant_id=tenant_id,
            )
            title_by_module = {mod.id: mod for mod in modules}

        details_by_id: dict[int, TeamActivityMemberDetail] = {}
        sk_role = HierarchyRole.SHASTIYA_KORMI.value
        for chw_id in detail_chw_ids:
            flags = _sk_sort_flags(chw_id, metrics.flags_by_chw)
            assigned_ids = metrics.assigned_by_chw.get(chw_id, set())
            member_completions = metrics.completions_by_chw.get(chw_id, {})
            chatbot = chatbot_by_chw.get(chw_id, {"total": 0, "unattributed": 0, "by_module": {}})
            last_activity = last_activity_by_chw.get(chw_id, {})
            refreshers = refreshers_by_chw.get(chw_id, {"generated": 0, "completed": 0})

            assigned_modules: list[TeamMemberModuleActivity] = []
            for module_id in sorted(assigned_ids, key=str):
                mod = title_by_module.get(module_id)
                completed_at = member_completions.get(module_id)
                assigned_modules.append(
                    TeamMemberModuleActivity(
                        module_id=module_id,
                        title=mod.title_localized if mod else None,
                        completed_in_range=completed_at is not None,
                        completed_at=completed_at,
                    )
                )

            chatbot_modules: list[TeamMemberChatbotModuleUsage] = []
            for module_id, query_count in sorted(
                chatbot["by_module"].items(),
                key=lambda item: (-item[1], str(item[0])),
            ):
                if module_id is None:
                    continue
                mod = title_by_module.get(module_id)
                chatbot_modules.append(
                    TeamMemberChatbotModuleUsage(
                        module_id=module_id,
                        title=mod.title_localized if mod else None,
                        query_count=query_count,
                    )
                )

            details_by_id[chw_id] = TeamActivityMemberDetail(
                user_id=chw_id,
                name=metrics.name_by_id.get(chw_id, str(chw_id)),
                role=sk_role,
                can_drill_down=False,
                is_active=flags.is_active,
                is_chatbot_engaged=flags.is_chatbot_engaged,
                last_chat_at=last_activity.get("last_chat_at"),
                last_active_at=last_activity.get("last_active_at"),
                has_completed_module_in_range=flags.has_completed_module_in_range,
                assigned_modules=assigned_modules,
                chatbot_query_count=_to_int(chatbot.get("total")),
                chatbot_unattributed_query_count=_to_int(chatbot.get("unattributed")),
                chatbot_modules=chatbot_modules,
                refreshers_generated=_to_int(refreshers.get("generated")),
                refreshers_completed=_to_int(refreshers.get("completed")),
                performance_status=(
                    PERFORMANCE_STATUS_ON_TRACK
                    if metrics.sk_on_track.get(chw_id, False)
                    else PERFORMANCE_STATUS_AT_RISK
                ),
                summary=None,
            )

        return details_by_id

    async def get_member_questions(
        self,
        *,
        scope: TeamActivityScope,
        user_id: int,
        from_date: date,
        to_date: date,
        limit: int,
        offset: int,
        tenant_id: int | None,
        geo_chw_ids: frozenset[int] | None = None,
    ) -> TeamMemberQuestionsResponse:
        hierarchy_tenant = tenant_id if tenant_id is not None else DEFAULT_TENANT_ID
        by_id = await org_user_index(self._session, tenant_id=hierarchy_tenant)
        if not is_team_activity_descendant(
            by_id,
            scope.viewer_id,
            user_id,
            unrestricted=scope.unrestricted,
        ):
            raise AppError(
                ErrorCode.FORBIDDEN.value,
                "user_id is outside the caller's team hierarchy",
                status=403,
            )

        if geo_chw_ids is not None and user_id not in geo_chw_ids:
            return TeamMemberQuestionsResponse(
                user_id=user_id,
                from_date=from_date,
                to_date=to_date,
                questions=[],
                total_questions=0,
                total_pages=0,
                limit=limit,
                offset=offset,
                server_time_utc=datetime.now(UTC).isoformat(),
            )

        total_questions = await self._count_member_questions(
            chw_id=user_id,
            from_date=from_date,
            to_date=to_date,
            tenant_id=tenant_id,
        )
        total_pages = (total_questions + limit - 1) // limit if total_questions > 0 else 0
        rows = await self._fetch_member_questions_page(
            chw_id=user_id,
            from_date=from_date,
            to_date=to_date,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )

        questions: list[TeamMemberQuestionItem] = []
        for row in rows:
            question = str(row.get("question") or "").strip()
            if not question:
                continue
            last_asked_at = _to_datetime(row.get("last_asked_at"))
            if last_asked_at is None:
                continue
            questions.append(
                TeamMemberQuestionItem(
                    question=question,
                    occurrence_count=_to_int(row.get("occurrence_count")),
                    last_asked_at=last_asked_at,
                )
            )

        return TeamMemberQuestionsResponse(
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            questions=questions,
            total_questions=total_questions,
            total_pages=total_pages,
            limit=limit,
            offset=offset,
            server_time_utc=datetime.now(UTC).isoformat(),
        )

    def _tenant_clause(self, tenant_id: int | None) -> tuple[str, dict[str, Any]]:
        if tenant_id is None:
            return "", {}
        return "  AND tenant_id = {tenant_id:Int64}\n", {"tenant_id": tenant_id}

    async def _count_member_questions(
        self,
        *,
        chw_id: int,
        from_date: date,
        to_date: date,
        tenant_id: int | None,
    ) -> int:
        tenant_clause, tenant_params = self._tenant_clause(tenant_id)
        query = f"""
        SELECT count() AS total_questions
        FROM (
          SELECT question_key
          FROM (
            SELECT {QUESTION_NORMALIZE_KEY_SQL} AS question_key
            FROM coaching_events
            WHERE chw_id = {{chw_id:Int64}}
              AND event_type = {{event_type:String}}
              AND event_date >= {{from_date:Date}}
              AND event_date <= {{to_date:Date}}
            {tenant_clause})
          WHERE length(question_key) > 0
          GROUP BY question_key
        )
        """
        parameters: dict[str, Any] = {
            "chw_id": chw_id,
            "event_type": _DIGITAL_HELP_EVENT,
            "from_date": from_date,
            "to_date": to_date,
            **tenant_params,
        }
        rows = await self._ch.query_rows(query, parameters=parameters)
        if not rows:
            return 0
        return _to_int(rows[0].get("total_questions"))

    async def _fetch_member_questions_page(
        self,
        *,
        chw_id: int,
        from_date: date,
        to_date: date,
        tenant_id: int | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        tenant_clause, tenant_params = self._tenant_clause(tenant_id)
        query = f"""
        SELECT
          argMax(raw_question, timestamp_local) AS question,
          count() AS occurrence_count,
          max(timestamp_local) AS last_asked_at
        FROM (
          SELECT
            {QUESTION_NORMALIZE_KEY_SQL} AS question_key,
            {QUESTION_EXTRACT_SQL} AS raw_question,
            timestamp_utc,
            timestamp_local
          FROM coaching_events
          WHERE chw_id = {{chw_id:Int64}}
              AND event_type = {{event_type:String}}
              AND event_date >= {{from_date:Date}}
              AND event_date <= {{to_date:Date}}
          {tenant_clause})
        WHERE length(question_key) > 0
        GROUP BY question_key
        ORDER BY max(timestamp_utc) DESC
        LIMIT {{limit:UInt32}}
        OFFSET {{offset:UInt32}}
        """
        parameters: dict[str, Any] = {
            "chw_id": chw_id,
            "event_type": _DIGITAL_HELP_EVENT,
            "from_date": from_date,
            "to_date": to_date,
            "limit": limit,
            "offset": offset,
            **tenant_params,
        }
        return await self._ch.query_rows(query, parameters=parameters)

    async def _fetch_daily_summary(
        self,
        *,
        chw_ids: list[int],
        from_date: date,
        to_date: date,
        tenant_id: int | None,
    ) -> dict[int, dict[str, Any]]:
        if not chw_ids:
            return {}
        tenant_clause, tenant_params = self._tenant_clause(tenant_id)
        query = f"""
        SELECT
          chw_id,
          sum(cards_shown + quiz_views + quiz_attempts) > 0 AS is_active,
          sum(digital_help_used) > 0 AS is_chatbot_engaged,
          sum(digital_help_used) AS chatbot_query_count
        FROM chw_daily_summary
        WHERE chw_id IN {{chw_ids:Array(Int64)}}
          AND event_date >= {{from_date:Date}}
          AND event_date <= {{to_date:Date}}
        {tenant_clause}GROUP BY chw_id
        """
        parameters: dict[str, Any] = {
            "chw_ids": chw_ids,
            "from_date": from_date,
            "to_date": to_date,
            **tenant_params,
        }
        rows = await self._ch.query_rows(query, parameters=parameters)
        out: dict[int, dict[str, Any]] = {}
        for row in rows:
            chw_id = _to_int(row.get("chw_id"), default=-1)
            if chw_id < 0:
                continue
            out[chw_id] = {
                "is_active": bool(row.get("is_active")),
                "is_chatbot_engaged": bool(row.get("is_chatbot_engaged")),
                "chatbot_query_count": _to_int(row.get("chatbot_query_count")),
            }
        return out

    async def _fetch_digital_help(
        self,
        *,
        chw_ids: list[int],
        from_date: date,
        to_date: date,
        tenant_id: int | None,
    ) -> dict[int, dict[str, Any]]:
        if not chw_ids:
            return {}
        tenant_clause, tenant_params = self._tenant_clause(tenant_id)
        query = f"""
        SELECT
          chw_id,
          module_id,
          sum(query_count) AS query_count
        FROM chw_digital_help_daily
        WHERE chw_id IN {{chw_ids:Array(Int64)}}
          AND event_date >= {{from_date:Date}}
          AND event_date <= {{to_date:Date}}
        {tenant_clause}GROUP BY chw_id, module_id
        """
        parameters: dict[str, Any] = {
            "chw_ids": chw_ids,
            "from_date": from_date,
            "to_date": to_date,
            **tenant_params,
        }
        rows = await self._ch.query_rows(query, parameters=parameters)
        out: dict[int, dict[str, Any]] = {}
        for row in rows:
            chw_id = _to_int(row.get("chw_id"), default=-1)
            if chw_id < 0:
                continue
            bucket = out.setdefault(
                chw_id,
                {"total": 0, "unattributed": 0, "by_module": {}},
            )
            module_id = _to_uuid(row.get("module_id"))
            count = _to_int(row.get("query_count"))
            bucket["total"] += count
            if module_id is None:
                bucket["unattributed"] += count
            else:
                bucket["by_module"][module_id] = bucket["by_module"].get(module_id, 0) + count
        return out

    async def _fetch_last_activity_timestamps(
        self,
        *,
        chw_ids: list[int],
        tenant_id: int | None,
    ) -> dict[int, dict[str, datetime | None]]:
        if not chw_ids:
            return {}
        tenant_clause, tenant_params = self._tenant_clause(tenant_id)
        query = f"""
        SELECT
          coalesce(chat.chw_id, active.chw_id) AS chw_id,
          chat.last_chat_date,
          active.last_active_date
        FROM (
          SELECT
            chw_id,
            max(event_date) AS last_chat_date
          FROM chw_digital_help_daily
          WHERE chw_id IN {{chw_ids:Array(Int64)}}
            AND query_count > 0
          {tenant_clause}GROUP BY chw_id
        ) AS chat
        FULL OUTER JOIN (
          SELECT
            chw_id,
            max(event_date) AS last_active_date
          FROM chw_daily_summary
          WHERE chw_id IN {{chw_ids:Array(Int64)}}
            AND (cards_shown + quiz_views + quiz_attempts) > 0
          {tenant_clause}GROUP BY chw_id
        ) AS active ON chat.chw_id = active.chw_id
        """
        parameters: dict[str, Any] = {
            "chw_ids": chw_ids,
            **tenant_params,
        }
        rows = await self._ch.query_rows(query, parameters=parameters)
        out: dict[int, dict[str, datetime | None]] = {}
        for row in rows:
            chw_id = _to_int(row.get("chw_id"), default=-1)
            if chw_id < 0:
                continue
            out[chw_id] = {
                "last_chat_at": _date_to_datetime_utc(row.get("last_chat_date")),
                "last_active_at": _date_to_datetime_utc(row.get("last_active_date")),
            }
        return out

    async def _fetch_quiz_attempts(
        self,
        *,
        chw_ids: list[int],
        from_date: date,
        to_date: date,
        tenant_id: int | None,
    ) -> list[dict[str, Any]]:
        if not chw_ids:
            return []
        tenant_clause, tenant_params = self._tenant_clause(tenant_id)
        query = f"""
        SELECT
          chw_id,
          quiz_id,
          outcome,
          timestamp_utc,
          id
        FROM coaching_events
        WHERE chw_id IN {{chw_ids:Array(Int64)}}
          AND event_type = 'module_quiz_attempted'
          AND event_date >= {{from_date:Date}}
          AND event_date <= {{to_date:Date}}
        {tenant_clause}ORDER BY chw_id, timestamp_utc ASC, id ASC
        """
        parameters: dict[str, Any] = {
            "chw_ids": chw_ids,
            "from_date": from_date,
            "to_date": to_date,
            **tenant_params,
        }
        return await self._ch.query_rows(query, parameters=parameters)

    async def _fetch_responsive_module_ids(
        self,
        *,
        chw_ids: list[int],
        from_date: date,
        to_date: date,
        tenant_id: int | None,
    ) -> dict[int, set[UUID]]:
        if not chw_ids:
            return {}
        tenant_clause, tenant_params = self._tenant_clause(tenant_id)
        query = f"""
        SELECT DISTINCT
          chw_id,
          module_id
        FROM coaching_events
        WHERE chw_id IN {{chw_ids:Array(Int64)}}
          AND event_type IN ('module_card_viewed', 'module_quiz_viewed', 'module_quiz_attempted')
          AND module_id IS NOT NULL
          AND event_date >= {{from_date:Date}}
          AND event_date <= {{to_date:Date}}
        {tenant_clause}
        """
        parameters: dict[str, Any] = {
            "chw_ids": chw_ids,
            "from_date": from_date,
            "to_date": to_date,
            **tenant_params,
        }
        rows = await self._ch.query_rows(query, parameters=parameters)
        out: dict[int, set[UUID]] = {}
        for row in rows:
            chw_id = _to_int(row.get("chw_id"), default=-1)
            module_id = _to_uuid(row.get("module_id"))
            if chw_id < 0 or module_id is None:
                continue
            out.setdefault(chw_id, set()).add(module_id)
        return out
