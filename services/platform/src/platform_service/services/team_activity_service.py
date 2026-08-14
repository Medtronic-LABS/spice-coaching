"""Team activity dashboard — hierarchy-scoped engagement and completion reporting."""

from __future__ import annotations

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
from mc_contracts.enums import HierarchyRole
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_identity import TeamActivityScope
from platform_service.clickhouse.client import ClickHouseClient
from platform_service.clickhouse.question_sql import QUESTION_EXTRACT_SQL, QUESTION_NORMALIZE_KEY_SQL
from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.repositories.module_completion_repository import ModuleCompletionRepository
from platform_service.db.repositories.module_repository import ModuleRepository
from platform_service.services.dashboard_hierarchy import (
    OrgUser,
    descendants_with_role,
    filter_users_by_chw_ids,
    is_team_activity_descendant,
    member_role_at_depth,
    org_user_index,
    sks_under_focus,
    sks_under_member,
)
from platform_service.services.sync.module_assignment_resolver import resolve_assigned_module_ids

_DIGITAL_HELP_EVENT = "digital_help_used"


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
    Per ``(chw_id, quiz_id)``: first ``incorrect`` opens a refresher; subsequent
    ``incorrect`` while open is a no-op; ``correct`` while open closes it.
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

        if outcome_str == "incorrect":
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


def _summary_from_sk_details(sk_details: list[TeamActivityMemberDetail]) -> TeamActivitySummary:
    """SK-counted summary for one drillable member (same fields as the envelope)."""
    total_users = len(sk_details)
    active_users = sum(1 for sk in sk_details if sk.is_active)
    return TeamActivitySummary(
        total_users=total_users,
        active_users=active_users,
        non_active_users=total_users - active_users,
        users_completed_module=sum(1 for sk in sk_details if sk.has_completed_module_in_range),
        users_chatbot_engaged=sum(1 for sk in sk_details if sk.is_chatbot_engaged),
    )


def _aggregate_member_from_sks(
    *,
    user_id: int,
    name: str,
    role: str,
    sk_details: list[TeamActivityMemberDetail],
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
            else sorted(
                descendants_with_role(by_id, focus_id, focus_role, member_role),
                key=lambda u: u.name,
            )
        )
        total_members = len(children)
        total_pages = (total_members + limit - 1) // limit if total_members > 0 else 0
        paged_children = children[offset : offset + limit]

        all_sks = filter_users_by_chw_ids(
            sks_under_focus(by_id, focus_id, focus_role),
            geo_chw_ids,
        )
        all_sk_members = [{"id": u.id, "name": u.name} for u in sorted(all_sks, key=lambda u: u.name)]
        all_chw_ids = [int(m["id"]) for m in all_sk_members]

        detail_chw_ids: list[int] = []
        sks_by_member: dict[int, list[int]] = {}
        if member_role == HierarchyRole.SHASTIYA_KORMI.value:
            detail_chw_ids = [u.id for u in filter_users_by_chw_ids(list(paged_children), geo_chw_ids)]
        elif member_role is None:
            # SK focus: no members; still build summary for that one SK.
            detail_chw_ids = []
        else:
            for member in paged_children:
                member_sks = filter_users_by_chw_ids(
                    sks_under_member(by_id, member),
                    geo_chw_ids,
                )
                sk_ids = [u.id for u in member_sks]
                sks_by_member[member.id] = sk_ids
                detail_chw_ids.extend(sk_ids)

        summary, details_by_id = await self._build_sk_activity(
            members=all_sk_members,
            detail_chw_ids=detail_chw_ids,
            all_chw_ids=all_chw_ids,
            from_date=from_date,
            to_date=to_date,
            tenant_id=tenant_id,
            hierarchy_tenant=hierarchy_tenant,
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
                )
                for member in paged_children
            ]

        return TeamActivityResponse(
            from_date=from_date,
            to_date=to_date,
            summary=summary,
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

    async def _build_sk_activity(
        self,
        *,
        members: list[dict[str, Any]],
        detail_chw_ids: list[int],
        all_chw_ids: list[int],
        from_date: date,
        to_date: date,
        tenant_id: int | None,
        hierarchy_tenant: int,
    ) -> tuple[TeamActivitySummary, dict[int, TeamActivityMemberDetail]]:
        """Compute SK summary over all members; full detail rows for detail_chw_ids only."""
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
            if comp.completed_at is not None:
                completions_by_chw.setdefault(comp.chw_id, {})[comp.module_family_id] = comp.completed_at

        assigned_by_chw: dict[int, set[UUID]] = {}
        family_ids_by_chw: dict[int, set[UUID]] = {}
        for member in members:
            chw_id = int(member["id"])
            assigned_ids = await resolve_assigned_module_ids(
                self._session,
                user_id=chw_id,
                tenant_id=hierarchy_tenant,
            )
            assigned_by_chw[chw_id] = assigned_ids
            if assigned_ids:
                modules = await ModuleRepository(self._session).list_modules_by_ids(
                    list(assigned_ids),
                    tenant_id=tenant_id,
                )
                family_ids_by_chw[chw_id] = {mod.module_family_id for mod in modules}
            else:
                family_ids_by_chw[chw_id] = set()

        active_users = 0
        users_chatbot_engaged = 0
        users_completed_module = 0
        for member in members:
            chw_id = int(member["id"])
            daily = daily_by_chw.get(chw_id, {})
            if daily.get("is_active"):
                active_users += 1
            if daily.get("is_chatbot_engaged"):
                users_chatbot_engaged += 1
            assigned_families = family_ids_by_chw.get(chw_id, set())
            member_completions = completions_by_chw.get(chw_id, {})
            if assigned_families & member_completions.keys():
                users_completed_module += 1

        summary = TeamActivitySummary(
            total_users=total_users,
            active_users=active_users,
            non_active_users=total_users - active_users,
            users_completed_module=users_completed_module,
            users_chatbot_engaged=users_chatbot_engaged,
        )

        if not detail_chw_ids:
            return summary, {}

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
            all_module_ids.update(assigned_by_chw.get(chw_id, set()))
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

        name_by_id = {int(m["id"]): str(m["name"]) for m in members}
        details_by_id: dict[int, TeamActivityMemberDetail] = {}
        sk_role = HierarchyRole.SHASTIYA_KORMI.value
        for chw_id in detail_chw_ids:
            daily = daily_by_chw.get(chw_id, {})
            assigned_ids = assigned_by_chw.get(chw_id, set())
            member_completions = completions_by_chw.get(chw_id, {})
            chatbot = chatbot_by_chw.get(chw_id, {"total": 0, "unattributed": 0, "by_module": {}})
            last_activity = last_activity_by_chw.get(chw_id, {})
            refreshers = refreshers_by_chw.get(chw_id, {"generated": 0, "completed": 0})

            assigned_modules: list[TeamMemberModuleActivity] = []
            for module_id in sorted(assigned_ids, key=str):
                mod = title_by_module.get(module_id)
                family_id = mod.module_family_id if mod else None
                completed_at = member_completions.get(family_id) if family_id else None
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

            assigned_families = family_ids_by_chw.get(chw_id, set())
            details_by_id[chw_id] = TeamActivityMemberDetail(
                user_id=chw_id,
                name=name_by_id.get(chw_id, str(chw_id)),
                role=sk_role,
                can_drill_down=False,
                is_active=bool(daily.get("is_active")),
                is_chatbot_engaged=bool(daily.get("is_chatbot_engaged")),
                last_chat_at=last_activity.get("last_chat_at"),
                last_active_at=last_activity.get("last_active_at"),
                has_completed_module_in_range=bool(assigned_families & member_completions.keys()),
                assigned_modules=assigned_modules,
                chatbot_query_count=_to_int(chatbot.get("total")),
                chatbot_unattributed_query_count=_to_int(chatbot.get("unattributed")),
                chatbot_modules=chatbot_modules,
                refreshers_generated=_to_int(refreshers.get("generated")),
                refreshers_completed=_to_int(refreshers.get("completed")),
                summary=None,
            )

        return summary, details_by_id

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
          argMax(raw_question, timestamp_utc) AS question,
          count() AS occurrence_count,
          max(timestamp_utc) AS last_asked_at
        FROM (
          SELECT
            {QUESTION_NORMALIZE_KEY_SQL} AS question_key,
            {QUESTION_EXTRACT_SQL} AS raw_question,
            timestamp_utc
          FROM coaching_events
          WHERE chw_id = {{chw_id:Int64}}
              AND event_type = {{event_type:String}}
              AND event_date >= {{from_date:Date}}
              AND event_date <= {{to_date:Date}}
          {tenant_clause})
        WHERE length(question_key) > 0
        GROUP BY question_key
        ORDER BY last_asked_at DESC
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
