"""Unit tests for TeamActivityService."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from mc_contracts.dashboard import (
    TeamActivityMemberDetail,
    TeamActivitySummary,
    TeamMemberChatbotModuleUsage,
    TeamMemberModuleActivity,
)
from mc_contracts.enums import HierarchyRole
from mc_foundation.problem import AppError
from platform_service.auth.spice_identity import TeamActivityScope
from platform_service.services.dashboard_hierarchy import (
    OrgUser,
    descendants_with_role,
    member_role_at_depth,
)
from platform_service.services.team_activity_service import (
    TeamActivityService,
    _aggregate_member_from_sks,
    _build_performance_status_by_user_id,
    _child_share_on_track,
    _completed_all_assigned,
    _count_refreshers,
    _sk_module_on_track,
)

ORGANIZER_ID = 401
AM_ID = 50
OTHER_AM_ID = 51
OTHER_PO_ID = 999


def _po_scope(organizer_id: int = ORGANIZER_ID) -> TeamActivityScope:
    return TeamActivityScope(viewer_id=organizer_id, unrestricted=False)


def _am_scope(viewer_id: int = AM_ID) -> TeamActivityScope:
    return TeamActivityScope(viewer_id=viewer_id, unrestricted=False)


def _unrestricted_scope(*, viewer_id: int | None = None) -> TeamActivityScope:
    return TeamActivityScope(viewer_id=viewer_id, unrestricted=True)


def _org_user(
    user_id: int,
    name: str,
    *,
    role: str,
    parent_id: int | None = None,
) -> OrgUser:
    return OrgUser(
        id=user_id,
        name=name,
        role=role,
        district_id=1,
        district=None,
        division_id=None,
        division=None,
        upazila_ids=frozenset(),
        upazila_names=frozenset(),
        parent_id=parent_id,
    )


def _patch_org_index(monkeypatch: pytest.MonkeyPatch, users: list[OrgUser]):
    index = {u.id: u for u in users}
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.org_user_index",
        AsyncMock(return_value=index),
    )


def _sk_detail(
    user_id: int,
    name: str,
    *,
    is_active: bool = False,
    is_chatbot_engaged: bool = False,
    chatbot_query_count: int = 0,
    chatbot_unattributed_query_count: int = 0,
    refreshers_generated: int = 0,
    refreshers_completed: int = 0,
    has_completed_module_in_range: bool = False,
    last_chat_at: datetime | None = None,
    last_active_at: datetime | None = None,
    assigned_modules: list[TeamMemberModuleActivity] | None = None,
    chatbot_modules: list[TeamMemberChatbotModuleUsage] | None = None,
    performance_status: str = "at_risk",
) -> TeamActivityMemberDetail:
    return TeamActivityMemberDetail(
        user_id=user_id,
        name=name,
        role=HierarchyRole.SHASTIYA_KORMI.value,
        can_drill_down=False,
        is_active=is_active,
        is_chatbot_engaged=is_chatbot_engaged,
        last_chat_at=last_chat_at,
        last_active_at=last_active_at,
        has_completed_module_in_range=has_completed_module_in_range,
        assigned_modules=assigned_modules or [],
        chatbot_query_count=chatbot_query_count,
        chatbot_unattributed_query_count=chatbot_unattributed_query_count,
        chatbot_modules=chatbot_modules or [],
        refreshers_generated=refreshers_generated,
        refreshers_completed=refreshers_completed,
        performance_status=performance_status,
    )


def _stub_assignments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleAssignmentRepository.list_module_ids_assigned_in_range_for_chws",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleCompletionRepository.list_completed_in_range_for_chws",
        AsyncMock(return_value=[]),
    )


def _stub_daily_rows(
    ch_client: MagicMock,
    rows: list[dict],
    *,
    responsive_rows: list[dict] | None = None,
) -> None:
    async def query_side_effect(query: str, parameters: dict | None = None) -> list[dict]:
        _ = parameters
        if "SELECT DISTINCT" in query and "module_card_viewed" in query:
            return list(responsive_rows or [])
        if "coaching_events" in query:
            return []
        if "last_chat_date" in query or "last_active_date" in query:
            return []
        if "chw_digital_help_daily" in query:
            return []
        if "chw_daily_summary" in query:
            return rows
        return []

    ch_client.query_rows = AsyncMock(side_effect=query_side_effect)


def _stub_assignments_by_chw(
    monkeypatch: pytest.MonkeyPatch,
    assigned_by_chw: dict[int, set[UUID]],
) -> None:
    async def list_assigned(
        _self: object,
        *,
        chw_ids: list[int],
        tenant_id: int,
        from_ts: object,
        to_ts: object,
    ) -> dict[int, set[UUID]]:
        _ = tenant_id, from_ts, to_ts
        return {chw_id: set(assigned_by_chw.get(chw_id, set())) for chw_id in chw_ids}

    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleAssignmentRepository.list_module_ids_assigned_in_range_for_chws",
        list_assigned,
    )
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleCompletionRepository.list_completed_in_range_for_chws",
        AsyncMock(return_value=[]),
    )
    modules = []
    seen: set[UUID] = set()
    for module_ids in assigned_by_chw.values():
        for module_id in module_ids:
            if module_id in seen:
                continue
            seen.add(module_id)
            mod = MagicMock()
            mod.id = module_id
            mod.module_family_id = uuid4()
            mod.title_localized = {"en": f"Module {module_id}"}
            modules.append(mod)
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleRepository.list_modules_by_ids",
        AsyncMock(return_value=modules),
    )


def _stub_assigned_modules_for_all_chws(
    monkeypatch: pytest.MonkeyPatch,
    module_ids: set[UUID],
) -> None:
    async def list_assigned(
        _self: object,
        *,
        chw_ids: list[int],
        tenant_id: int,
        from_ts: object,
        to_ts: object,
    ) -> dict[int, set[UUID]]:
        _ = tenant_id, from_ts, to_ts
        return {chw_id: set(module_ids) for chw_id in chw_ids}

    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleAssignmentRepository.list_module_ids_assigned_in_range_for_chws",
        list_assigned,
    )


@pytest.fixture
def ch_client() -> MagicMock:
    client = MagicMock()
    client.query_rows = AsyncMock(return_value=[])
    return client


@pytest.fixture
def session() -> MagicMock:
    return MagicMock()


def test_completed_all_assigned_requires_nonempty_subset() -> None:
    a = uuid4()
    b = uuid4()
    assert _completed_all_assigned(set(), {a}) is False
    assert _completed_all_assigned({a}, set()) is False
    assert _completed_all_assigned({a, b}, {a}) is False
    assert _completed_all_assigned({a}, {a, b}) is True
    assert _completed_all_assigned({a, b}, {a, b}) is True


def test_count_refreshers_incorrect_then_correct() -> None:
    quiz_a = uuid4()
    counts = _count_refreshers(
        [
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "correct"},
        ]
    )
    assert counts[1]["generated"] == 1
    assert counts[1]["completed"] == 1


def test_count_refreshers_wrong_then_correct() -> None:
    quiz_a = uuid4()
    counts = _count_refreshers(
        [
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "wrong"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "correct"},
        ]
    )
    assert counts[1]["generated"] == 1
    assert counts[1]["completed"] == 1


def test_count_refreshers_wrong_and_incorrect_are_same_open() -> None:
    quiz_a = uuid4()
    counts = _count_refreshers(
        [
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "wrong"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "correct"},
        ]
    )
    assert counts[1]["generated"] == 1
    assert counts[1]["completed"] == 1


def test_count_refreshers_second_incorrect_is_noop() -> None:
    quiz_a = uuid4()
    counts = _count_refreshers(
        [
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "correct"},
        ]
    )
    assert counts[1]["generated"] == 1
    assert counts[1]["completed"] == 1


def test_count_refreshers_correct_without_open_is_noop() -> None:
    quiz_a = uuid4()
    counts = _count_refreshers(
        [
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "correct"},
        ]
    )
    assert counts[1]["generated"] == 0
    assert counts[1]["completed"] == 0


def test_count_refreshers_reopen_after_close() -> None:
    quiz_a = uuid4()
    counts = _count_refreshers(
        [
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "correct"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "incorrect"},
        ]
    )
    assert counts[1]["generated"] == 2
    assert counts[1]["completed"] == 1


def test_count_refreshers_independent_quizzes() -> None:
    quiz_a = uuid4()
    quiz_b = uuid4()
    counts = _count_refreshers(
        [
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": quiz_b, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "correct"},
        ]
    )
    assert counts[1]["generated"] == 2
    assert counts[1]["completed"] == 1


def test_count_refreshers_independent_chws() -> None:
    quiz_a = uuid4()
    counts = _count_refreshers(
        [
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "incorrect"},
            {"chw_id": 2, "quiz_id": quiz_a, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "correct"},
        ]
    )
    assert counts[1]["generated"] == 1
    assert counts[1]["completed"] == 1
    assert counts[2]["generated"] == 1
    assert counts[2]["completed"] == 0


def test_count_refreshers_skips_malformed_rows() -> None:
    quiz_a = uuid4()
    counts = _count_refreshers(
        [
            {"chw_id": None, "quiz_id": quiz_a, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": None, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": None},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "  "},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "incorrect"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "CORRECT"},
        ]
    )
    assert counts[1]["generated"] == 1
    assert counts[1]["completed"] == 1


def test_count_refreshers_wrong_is_case_insensitive() -> None:
    quiz_a = uuid4()
    counts = _count_refreshers(
        [
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "WRONG"},
            {"chw_id": 1, "quiz_id": quiz_a, "outcome": "correct"},
        ]
    )
    assert counts[1]["generated"] == 1
    assert counts[1]["completed"] == 1


def test_count_refreshers_empty() -> None:
    assert _count_refreshers([]) == {}


async def test_empty_team_returns_zero_summary(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [_org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID)],
    )
    _stub_assignments(monkeypatch)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.summary.total_users == 0
    assert resp.summary.active_users == 0
    assert resp.summary.non_active_users == 0
    assert resp.members == []
    assert resp.total_members == 0
    assert resp.focus_user_id is None
    ch_client.query_rows.assert_not_awaited()


async def test_admin_default_lists_ams_excludes_orphan_sks(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM Alpha", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "AM Beta", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO Alpha", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Beta", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
            _org_user(393, "Orphan SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=None),
        ],
    )
    _stub_assignments(monkeypatch)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.focus_user_id is None
    assert resp.summary.total_users == 2
    assert resp.total_members == 2
    assert [m.user_id for m in resp.members] == [AM_ID, OTHER_AM_ID]
    assert all(m.role == HierarchyRole.AREA_MANAGER.value for m in resp.members)
    assert all(m.can_drill_down is True for m in resp.members)
    by_id = {m.user_id: m for m in resp.members}
    assert by_id[AM_ID].summary == TeamActivitySummary(
        total_users=1,
        active_users=0,
        non_active_users=1,
        users_completed_module=0,
        users_chatbot_engaged=0,
    )
    assert by_id[OTHER_AM_ID].summary == TeamActivitySummary(
        total_users=1,
        active_users=0,
        non_active_users=1,
        users_completed_module=0,
        users_chatbot_engaged=0,
    )


async def test_geo_filter_narrows_sk_summary_keeps_po_members(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sk_a = 395
    sk_b = 396
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM Alpha", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO Alpha", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(sk_a, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(sk_b, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    resp_all = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=AM_ID,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
        depth=0,
        geo_chw_ids=None,
    )
    assert resp_all.summary.total_users == 2
    assert resp_all.total_members == 1
    assert resp_all.members[0].user_id == ORGANIZER_ID
    assert resp_all.members[0].summary == TeamActivitySummary(
        total_users=2,
        active_users=0,
        non_active_users=2,
        users_completed_module=0,
        users_chatbot_engaged=0,
    )

    resp_filtered = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=AM_ID,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
        depth=0,
        geo_chw_ids=frozenset({sk_a}),
    )
    assert resp_filtered.summary.total_users == 1
    assert resp_filtered.total_members == 1
    assert resp_filtered.members[0].user_id == ORGANIZER_ID
    assert resp_filtered.members[0].is_active is False
    assert resp_filtered.members[0].summary == TeamActivitySummary(
        total_users=1,
        active_users=0,
        non_active_users=1,
        users_completed_module=0,
        users_chatbot_engaged=0,
    )


async def test_admin_drill_am_lists_pos(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM One", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "AM Two", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO Mine", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Other", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(395, "Mine SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Other SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    async def query_side_effect(query: str, parameters: dict | None = None) -> list[dict]:
        _ = query
        if parameters and "chw_ids" in parameters:
            if "chw_daily_summary" in query and "last_active_date" not in query:
                return [{"chw_id": 395, "is_active": 1, "is_chatbot_engaged": 0, "chatbot_query_count": 0}]
            return []
        return []

    ch_client.query_rows = AsyncMock(side_effect=query_side_effect)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=AM_ID,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.focus_user_id == AM_ID
    assert resp.summary.total_users == 1
    assert resp.summary.active_users == 1
    assert resp.total_members == 1
    assert resp.members[0].user_id == ORGANIZER_ID
    assert resp.members[0].role == HierarchyRole.PO.value
    assert resp.members[0].can_drill_down is True
    assert resp.members[0].is_active is True
    assert resp.members[0].summary == TeamActivitySummary(
        total_users=1,
        active_users=1,
        non_active_users=0,
        users_completed_module=0,
        users_chatbot_engaged=0,
    )


async def test_admin_drill_po_lists_sks(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=ORGANIZER_ID,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.focus_user_id == ORGANIZER_ID
    assert resp.total_users == 2
    assert [m.user_id for m in resp.members] == [395, 394]
    assert all(m.role == HierarchyRole.SHASTIYA_KORMI.value for m in resp.members)
    assert all(m.can_drill_down is False for m in resp.members)
    assert all(m.summary is None for m in resp.members)


async def test_sk_focus_empty_members_single_sk_summary(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    async def query_side_effect(query: str, parameters: dict | None = None) -> list[dict]:
        _ = query
        if parameters and "chw_ids" in parameters:
            if "chw_daily_summary" in query and "last_active_date" not in query:
                return [{"chw_id": 395, "is_active": 1, "is_chatbot_engaged": 1, "chatbot_query_count": 2}]
            return []
        return []

    ch_client.query_rows = AsyncMock(side_effect=query_side_effect)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=395,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.focus_user_id == 395
    assert resp.members == []
    assert resp.total_members == 0
    assert resp.total_users == 1
    assert resp.summary.total_users == 1
    assert resp.summary.active_users == 1
    assert resp.summary.users_chatbot_engaged == 1


async def test_po_cannot_focus_foreign_am(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )

    with pytest.raises(AppError) as exc_info:
        await TeamActivityService(ch_client, session).get_team_activity(
            scope=_po_scope(),
            focus_user_id=AM_ID,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=50,
            offset=0,
            tenant_id=None,
        )
    assert exc_info.value.status == 403


async def test_user_id_self_same_as_default(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    default_resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )
    self_resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=ORGANIZER_ID,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert [m.user_id for m in default_resp.members] == [m.user_id for m in self_resp.members]
    assert default_resp.total_users == self_resp.total_users
    assert default_resp.focus_user_id is None
    assert self_resp.focus_user_id == ORGANIZER_ID


async def test_summary_active_and_chatbot_flags(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    async def query_side_effect(query: str, parameters: dict | None = None) -> list[dict]:
        _ = query
        if parameters and "chw_ids" in parameters:
            if "coaching_events" in query:
                return []
            if "chw_digital_help_daily" in query and "last_chat_date" in query:
                return []
            if "chw_digital_help_daily" in query:
                return []
            if "chw_daily_summary" in query and "last_active_date" in query:
                return []
            return [
                {"chw_id": 395, "is_active": 1, "is_chatbot_engaged": 1, "chatbot_query_count": 3},
                {"chw_id": 394, "is_active": 0, "is_chatbot_engaged": 0, "chatbot_query_count": 0},
            ]
        return []

    ch_client.query_rows = AsyncMock(side_effect=query_side_effect)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.summary.total_users == 2
    assert resp.summary.active_users == 1
    assert resp.summary.non_active_users == 1
    assert resp.summary.users_chatbot_engaged == 1
    assert resp.members[0].user_id == 395
    assert resp.members[0].is_active is True
    assert resp.members[0].refreshers_generated == 0
    assert resp.members[0].refreshers_completed == 0
    assert resp.members[1].is_active is False


async def test_chatbot_unattributed_queries(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_id = uuid4()
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    async def query_side_effect(query: str, parameters: dict | None = None) -> list[dict]:
        _ = parameters
        if "coaching_events" in query:
            return []
        if "chw_daily_summary" in query:
            return [{"chw_id": 395, "is_active": 0, "is_chatbot_engaged": 1, "chatbot_query_count": 5}]
        if "chw_digital_help_daily" in query and "last_chat_date" in query:
            return []
        if "chw_digital_help_daily" in query:
            return [
                {"chw_id": 395, "module_id": str(module_id), "query_count": 2},
                {"chw_id": 395, "module_id": None, "query_count": 3},
            ]
        if "chw_daily_summary" in query and "last_active_date" in query:
            return []
        return []

    ch_client.query_rows = AsyncMock(side_effect=query_side_effect)
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleRepository.list_modules_by_ids",
        AsyncMock(return_value=[]),
    )

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    user = resp.members[0]
    assert user.chatbot_query_count == 5
    assert user.chatbot_unattributed_query_count == 3
    assert len(user.chatbot_modules) == 1
    assert user.chatbot_modules[0].module_id == module_id
    assert user.chatbot_modules[0].query_count == 2


async def test_module_completion_in_range(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family_id = uuid4()
    module_id = uuid4()
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assigned_modules_for_all_chws(monkeypatch, {module_id})

    completion = MagicMock()
    completion.chw_id = 395
    completion.module_family_id = family_id
    completion.latest_completed_module_id = module_id
    completion.completed_at = datetime(2026, 1, 15, tzinfo=UTC)
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleCompletionRepository.list_completed_in_range_for_chws",
        AsyncMock(return_value=[completion]),
    )

    mod = MagicMock()
    mod.id = module_id
    mod.module_family_id = family_id
    mod.title_localized = {"en": "Test Module"}
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleRepository.list_modules_by_ids",
        AsyncMock(return_value=[mod]),
    )

    ch_client.query_rows = AsyncMock(return_value=[])

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.summary.users_completed_module == 1
    assert resp.members[0].has_completed_module_in_range is True
    assert resp.members[0].assigned_modules[0].completed_in_range is True


async def test_users_completed_module_requires_all_assigned(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_a = uuid4()
    module_b = uuid4()
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assigned_modules_for_all_chws(monkeypatch, {module_a, module_b})

    completion = MagicMock()
    completion.chw_id = 395
    completion.module_family_id = uuid4()
    completion.latest_completed_module_id = module_a
    completion.completed_at = datetime(2026, 1, 15, tzinfo=UTC)
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleCompletionRepository.list_completed_in_range_for_chws",
        AsyncMock(return_value=[completion]),
    )

    modules = []
    for module_id, title in ((module_a, "A"), (module_b, "B")):
        mod = MagicMock()
        mod.id = module_id
        mod.module_family_id = uuid4()
        mod.title_localized = {"en": title}
        modules.append(mod)
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleRepository.list_modules_by_ids",
        AsyncMock(return_value=modules),
    )
    ch_client.query_rows = AsyncMock(return_value=[])

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.summary.users_completed_module == 0
    assert resp.members[0].has_completed_module_in_range is True
    completed_flags = {m.module_id: m.completed_in_range for m in resp.members[0].assigned_modules}
    assert completed_flags[module_a] is True
    assert completed_flags[module_b] is False


async def test_users_completed_module_zero_assigned_not_counted(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)
    ch_client.query_rows = AsyncMock(return_value=[])

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.summary.users_completed_module == 0
    assert resp.members[0].has_completed_module_in_range is False
    assert resp.members[0].assigned_modules == []


async def test_last_activity_timestamps(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    last_chat_date = date(2026, 2, 10)
    last_active_date = date(2026, 2, 8)
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    async def query_side_effect(query: str, parameters: dict | None = None) -> list[dict]:
        _ = parameters
        if "coaching_events" in query:
            return []
        if "last_chat_date" in query or "last_active_date" in query:
            return [
                {
                    "chw_id": 395,
                    "last_chat_date": last_chat_date,
                    "last_active_date": last_active_date,
                }
            ]
        if "chw_daily_summary" in query:
            return [{"chw_id": 395, "is_active": 1, "is_chatbot_engaged": 1, "chatbot_query_count": 2}]
        if "chw_digital_help_daily" in query:
            return []
        return []

    ch_client.query_rows = AsyncMock(side_effect=query_side_effect)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    user = resp.members[0]
    assert user.last_chat_at == datetime(2026, 2, 10, tzinfo=UTC)
    assert user.last_active_at == datetime(2026, 2, 8, tzinfo=UTC)


async def test_refresher_counts_from_coaching_events(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_a = uuid4()
    quiz_b = uuid4()
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    async def query_side_effect(query: str, parameters: dict | None = None) -> list[dict]:
        if "SELECT DISTINCT" in query and "module_card_viewed" in query:
            return []
        if "coaching_events" in query:
            assert parameters is not None
            assert parameters["chw_ids"] == [395]
            assert parameters["from_date"] == date(2026, 1, 1)
            assert parameters["to_date"] == date(2026, 1, 31)
            assert "module_quiz_attempted" in query
            assert "ORDER BY chw_id, timestamp_utc ASC, id ASC" in query
            return [
                {
                    "chw_id": 395,
                    "quiz_id": str(quiz_a),
                    "outcome": "incorrect",
                    "timestamp_utc": datetime(2026, 1, 2, tzinfo=UTC),
                    "id": "e1",
                },
                {
                    "chw_id": 395,
                    "quiz_id": str(quiz_a),
                    "outcome": "incorrect",
                    "timestamp_utc": datetime(2026, 1, 3, tzinfo=UTC),
                    "id": "e2",
                },
                {
                    "chw_id": 395,
                    "quiz_id": str(quiz_a),
                    "outcome": "correct",
                    "timestamp_utc": datetime(2026, 1, 4, tzinfo=UTC),
                    "id": "e3",
                },
                {
                    "chw_id": 395,
                    "quiz_id": str(quiz_b),
                    "outcome": "incorrect",
                    "timestamp_utc": datetime(2026, 1, 5, tzinfo=UTC),
                    "id": "e4",
                },
            ]
        if "chw_daily_summary" in query:
            return [{"chw_id": 395, "is_active": 1, "is_chatbot_engaged": 0, "chatbot_query_count": 0}]
        if "chw_digital_help_daily" in query:
            return []
        return []

    ch_client.query_rows = AsyncMock(side_effect=query_side_effect)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    user = resp.members[0]
    assert user.refreshers_generated == 2
    assert user.refreshers_completed == 1


@pytest.mark.asyncio
async def test_member_questions_forbidden_for_off_team_user(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "A", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )

    with pytest.raises(AppError) as exc_info:
        await TeamActivityService(ch_client, session).get_member_questions(
            scope=_po_scope(),
            user_id=999,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=50,
            offset=0,
            tenant_id=None,
        )
    assert exc_info.value.status == 403
    ch_client.query_rows.assert_not_awaited()


@pytest.mark.asyncio
async def test_member_questions_forbidden_for_unknown_user(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
        ],
    )

    with pytest.raises(AppError) as exc_info:
        await TeamActivityService(ch_client, session).get_member_questions(
            scope=_unrestricted_scope(viewer_id=999),
            user_id=395,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=50,
            offset=0,
            tenant_id=None,
        )
    assert exc_info.value.status == 403
    ch_client.query_rows.assert_not_awaited()


@pytest.mark.asyncio
async def test_member_questions_allows_self(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "A", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )

    async def _query_rows(query: str, parameters: dict | None = None) -> list[dict]:
        if "total_questions" in query:
            return [{"total_questions": 0}]
        return []

    ch_client.query_rows = AsyncMock(side_effect=_query_rows)

    resp = await TeamActivityService(ch_client, session).get_member_questions(
        scope=_po_scope(),
        user_id=ORGANIZER_ID,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )
    assert resp.user_id == ORGANIZER_ID
    assert resp.total_questions == 0
    assert resp.questions == []


@pytest.mark.asyncio
async def test_member_questions_am_can_query_descendant_sk(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "Other PO", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(OTHER_AM_ID, "Other AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(395, "A", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(396, "Other SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
        ],
    )

    async def _query_rows(query: str, parameters: dict | None = None) -> list[dict]:
        if "total_questions" in query:
            return [{"total_questions": 0}]
        return []

    ch_client.query_rows = AsyncMock(side_effect=_query_rows)

    resp = await TeamActivityService(ch_client, session).get_member_questions(
        scope=_am_scope(),
        user_id=395,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )
    assert resp.user_id == 395

    with pytest.raises(AppError) as exc_info:
        await TeamActivityService(ch_client, session).get_member_questions(
            scope=_am_scope(),
            user_id=396,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=50,
            offset=0,
            tenant_id=None,
        )
    assert exc_info.value.status == 403


@pytest.mark.asyncio
async def test_member_questions_unrestricted_allows_org_map_user(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "A", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )

    async def _query_rows(query: str, parameters: dict | None = None) -> list[dict]:
        if "total_questions" in query:
            return [{"total_questions": 0}]
        return []

    ch_client.query_rows = AsyncMock(side_effect=_query_rows)

    resp = await TeamActivityService(ch_client, session).get_member_questions(
        scope=_unrestricted_scope(viewer_id=999),
        user_id=395,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )
    assert resp.user_id == 395


@pytest.mark.asyncio
async def test_member_questions_returns_paginated_rows(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "A", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    last_asked = datetime(2026, 1, 15, 12, 0)

    async def _query_rows(query: str, parameters: dict | None = None) -> list[dict]:
        if "total_questions" in query:
            return [{"total_questions": 3}]
        return [
            {
                "question": "How do I measure RR?",
                "occurrence_count": 2,
                "last_asked_at": last_asked,
            },
            {
                "question": "child fever",
                "occurrence_count": 1,
                "last_asked_at": datetime(2026, 1, 10, 8, 0),
            },
        ]

    ch_client.query_rows = AsyncMock(side_effect=_query_rows)

    resp = await TeamActivityService(ch_client, session).get_member_questions(
        scope=_po_scope(),
        user_id=395,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=2,
        offset=0,
        tenant_id=None,
    )

    assert resp.user_id == 395
    assert resp.total_questions == 3
    assert resp.total_pages == 2
    assert resp.limit == 2
    assert len(resp.questions) == 2
    assert resp.questions[0].question == "How do I measure RR?"
    assert resp.questions[0].occurrence_count == 2
    assert resp.questions[0].last_asked_at == last_asked
    assert ch_client.query_rows.await_count == 2
    page_call = ch_client.query_rows.await_args_list[1]
    assert page_call.kwargs["parameters"]["chw_id"] == 395
    assert page_call.kwargs["parameters"]["limit"] == 2
    assert page_call.kwargs["parameters"]["offset"] == 0
    assert "digital_help_used" in page_call.kwargs["parameters"]["event_type"]
    assert "max(timestamp_local) AS last_asked_at" in page_call.args[0]
    assert "argMax(raw_question, timestamp_local)" in page_call.args[0]
    assert "ORDER BY max(timestamp_utc) DESC" in page_call.args[0]


@pytest.mark.asyncio
async def test_member_questions_skips_blank_question_rows(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "A", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )

    async def _query_rows(query: str, parameters: dict | None = None) -> list[dict]:
        if "total_questions" in query:
            return [{"total_questions": 1}]
        return [
            {"question": "  ", "occurrence_count": 1, "last_asked_at": datetime(2026, 1, 15, tzinfo=UTC)},
            {
                "question": "fever",
                "occurrence_count": 1,
                "last_asked_at": datetime(2026, 1, 14, tzinfo=UTC),
            },
        ]

    ch_client.query_rows = AsyncMock(side_effect=_query_rows)

    resp = await TeamActivityService(ch_client, session).get_member_questions(
        scope=_po_scope(),
        user_id=395,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert len(resp.questions) == 1
    assert resp.questions[0].question == "fever"


def test_aggregate_member_empty_sks() -> None:
    agg = _aggregate_member_from_sks(
        user_id=ORGANIZER_ID,
        name="PO",
        role=HierarchyRole.PO.value,
        sk_details=[],
        performance_status="at_risk",
    )
    assert agg.user_id == ORGANIZER_ID
    assert agg.role == HierarchyRole.PO.value
    assert agg.can_drill_down is True
    assert agg.is_active is False
    assert agg.chatbot_query_count == 0
    assert agg.summary == TeamActivitySummary(
        total_users=0,
        active_users=0,
        non_active_users=0,
        users_completed_module=0,
        users_chatbot_engaged=0,
    )


def test_aggregate_member_or_flags_sums_and_module_union() -> None:
    module_a = uuid4()
    module_b = uuid4()
    earlier = datetime(2026, 1, 10, tzinfo=UTC)
    later = datetime(2026, 1, 20, tzinfo=UTC)
    sks = [
        _sk_detail(
            1,
            "A",
            is_active=True,
            chatbot_query_count=2,
            chatbot_unattributed_query_count=1,
            refreshers_generated=1,
            refreshers_completed=0,
            last_chat_at=earlier,
            last_active_at=later,
            assigned_modules=[
                TeamMemberModuleActivity(
                    module_id=module_a,
                    title=None,
                    completed_in_range=True,
                    completed_at=earlier,
                )
            ],
            chatbot_modules=[
                TeamMemberChatbotModuleUsage(module_id=module_a, title=None, query_count=2),
            ],
        ),
        _sk_detail(
            2,
            "B",
            is_chatbot_engaged=True,
            has_completed_module_in_range=True,
            chatbot_query_count=3,
            refreshers_generated=2,
            refreshers_completed=1,
            last_chat_at=later,
            assigned_modules=[
                TeamMemberModuleActivity(
                    module_id=module_a,
                    title=None,
                    completed_in_range=False,
                    completed_at=None,
                ),
                TeamMemberModuleActivity(
                    module_id=module_b,
                    title=None,
                    completed_in_range=True,
                    completed_at=later,
                ),
            ],
            chatbot_modules=[
                TeamMemberChatbotModuleUsage(module_id=module_a, title=None, query_count=1),
            ],
        ),
    ]
    agg = _aggregate_member_from_sks(
        user_id=ORGANIZER_ID,
        name="PO",
        role=HierarchyRole.PO.value,
        sk_details=sks,
        performance_status="on_track",
    )
    assert agg.is_active is True
    assert agg.is_chatbot_engaged is True
    assert agg.has_completed_module_in_range is True
    assert agg.chatbot_query_count == 5
    assert agg.chatbot_unattributed_query_count == 1
    assert agg.refreshers_generated == 3
    assert agg.refreshers_completed == 1
    assert agg.last_chat_at == later
    assert agg.last_active_at == later
    assert {m.module_id for m in agg.assigned_modules} == {module_a, module_b}
    module_a_row = next(m for m in agg.assigned_modules if m.module_id == module_a)
    assert module_a_row.completed_in_range is True
    assert module_a_row.completed_at == earlier
    assert len(agg.chatbot_modules) == 1
    assert agg.chatbot_modules[0].query_count == 3
    assert agg.summary == TeamActivitySummary(
        total_users=2,
        active_users=1,
        non_active_users=1,
        users_completed_module=1,
        users_chatbot_engaged=1,
    )


async def test_am_default_lists_descendant_pos_only(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM One", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "AM Two", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO Mine", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Other", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(395, "Mine SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Other SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    async def query_side_effect(query: str, parameters: dict | None = None) -> list[dict]:
        _ = query
        if parameters and "chw_ids" in parameters:
            if "chw_daily_summary" in query and "last_active_date" not in query:
                return [{"chw_id": 395, "is_active": 1, "is_chatbot_engaged": 0, "chatbot_query_count": 0}]
            return []
        return []

    ch_client.query_rows = AsyncMock(side_effect=query_side_effect)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_am_scope(AM_ID),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.summary.total_users == 1
    assert resp.summary.active_users == 1
    assert resp.total_members == 1
    assert resp.members[0].user_id == ORGANIZER_ID
    assert resp.members[0].role == HierarchyRole.PO.value
    assert resp.members[0].can_drill_down is True
    assert resp.members[0].is_active is True
    assert resp.members[0].summary == TeamActivitySummary(
        total_users=1,
        active_users=1,
        non_active_users=0,
        users_completed_module=0,
        users_chatbot_engaged=0,
    )


async def test_pagination_pages_current_level_keeps_full_sk_summary(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(10, "PO A", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(11, "PO B", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(20, "SK A", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=10),
            _org_user(21, "SK B", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=11),
        ],
    )
    _stub_assignments(monkeypatch)

    async def query_side_effect(query: str, parameters: dict | None = None) -> list[dict]:
        if parameters and "chw_ids" in parameters and "chw_daily_summary" in query:
            if "last_active_date" in query:
                return []
            return [
                {"chw_id": 20, "is_active": 1, "is_chatbot_engaged": 0, "chatbot_query_count": 0},
                {"chw_id": 21, "is_active": 1, "is_chatbot_engaged": 0, "chatbot_query_count": 0},
            ]
        return []

    ch_client.query_rows = AsyncMock(side_effect=query_side_effect)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_am_scope(AM_ID),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=1,
        offset=0,
        tenant_id=None,
    )

    assert resp.summary.total_users == 2
    assert resp.summary.active_users == 2
    assert resp.total_members == 2
    assert resp.total_pages == 2
    assert len(resp.members) == 1
    assert resp.members[0].user_id == 10


async def test_name_query_filters_current_level_keeps_sk_summary(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alice SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Bob SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)
    _stub_daily_rows(ch_client, [])

    kwargs = {
        "scope": _po_scope(),
        "focus_user_id": None,
        "from_date": date(2026, 1, 1),
        "to_date": date(2026, 1, 31),
        "tenant_id": None,
    }
    unfiltered = await TeamActivityService(ch_client, session).get_team_activity(
        limit=50,
        offset=0,
        **kwargs,
    )
    matched = await TeamActivityService(ch_client, session).get_team_activity(
        limit=50,
        offset=0,
        name_query="alice",
        **kwargs,
    )
    paged = await TeamActivityService(ch_client, session).get_team_activity(
        limit=1,
        offset=0,
        name_query="SK",
        **kwargs,
    )

    assert [m.user_id for m in unfiltered.members] == [395, 394]
    assert unfiltered.total_members == 2
    assert unfiltered.summary.total_users == 2
    assert unfiltered.total_users == 2

    assert [m.user_id for m in matched.members] == [395]
    assert matched.members[0].name == "Alice SK"
    assert matched.total_members == 1
    assert matched.total_pages == 1
    assert matched.summary.total_users == 2
    assert matched.total_users == 2

    assert paged.total_members == 2
    assert paged.total_pages == 2
    assert len(paged.members) == 1
    assert paged.members[0].user_id == 395
    assert paged.summary.total_users == 2
    assert paged.total_users == 2


def test_member_role_at_depth_matrix() -> None:
    am = HierarchyRole.AREA_MANAGER.value
    po = HierarchyRole.PO.value
    sk = HierarchyRole.SHASTIYA_KORMI.value

    assert member_role_at_depth(None, 0) == am
    assert member_role_at_depth(None, 1) == po
    assert member_role_at_depth(None, 2) == sk
    assert member_role_at_depth(None, 3) is None

    assert member_role_at_depth(am, 0) == po
    assert member_role_at_depth(am, 1) == sk
    assert member_role_at_depth(am, 2) is None

    assert member_role_at_depth(po, 0) == sk
    assert member_role_at_depth(po, 1) is None

    assert member_role_at_depth(sk, 0) is None
    assert member_role_at_depth(sk, 1) is None


def test_descendants_with_role_excludes_orphan_pos() -> None:
    orphan_po = 888
    by_id = {
        AM_ID: _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
        ORGANIZER_ID: _org_user(ORGANIZER_ID, "PO Under AM", role=HierarchyRole.PO.value, parent_id=AM_ID),
        orphan_po: _org_user(orphan_po, "Orphan PO", role=HierarchyRole.PO.value, parent_id=None),
    }
    pos = descendants_with_role(by_id, None, None, HierarchyRole.PO.value)
    assert [u.id for u in pos] == [ORGANIZER_ID]


async def test_admin_depth_1_lists_pos_excludes_orphans(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orphan_po = 888
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM Alpha", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "AM Beta", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO Alpha", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Beta", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(orphan_po, "Orphan PO", role=HierarchyRole.PO.value, parent_id=None),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
        depth=1,
    )

    assert resp.focus_user_id is None
    assert resp.summary.total_users == 2
    assert resp.total_members == 2
    assert [m.user_id for m in resp.members] == [ORGANIZER_ID, OTHER_PO_ID]
    assert all(m.role == HierarchyRole.PO.value for m in resp.members)
    assert all(m.can_drill_down is True for m in resp.members)
    by_id = {m.user_id: m for m in resp.members}
    assert by_id[ORGANIZER_ID].summary == TeamActivitySummary(
        total_users=1,
        active_users=0,
        non_active_users=1,
        users_completed_module=0,
        users_chatbot_engaged=0,
    )
    assert by_id[OTHER_PO_ID].summary == TeamActivitySummary(
        total_users=1,
        active_users=0,
        non_active_users=1,
        users_completed_module=0,
        users_chatbot_engaged=0,
    )


async def test_admin_depth_2_lists_sks(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM Alpha", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "AM Beta", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO Alpha", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Beta", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
            _org_user(393, "Orphan SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=None),
        ],
    )
    _stub_assignments(monkeypatch)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
        depth=2,
    )

    assert resp.summary.total_users == 2
    assert resp.total_members == 2
    assert [m.user_id for m in resp.members] == [395, 394]
    assert all(m.role == HierarchyRole.SHASTIYA_KORMI.value for m in resp.members)
    assert all(m.can_drill_down is False for m in resp.members)
    assert all(m.summary is None for m in resp.members)


async def test_am_depth_1_lists_sks(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "Other AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO Mine", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Other", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(395, "Mine SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(396, "Mine SK2", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Other SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_am_scope(AM_ID),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
        depth=1,
    )

    assert resp.summary.total_users == 2
    assert resp.total_members == 2
    assert [m.user_id for m in resp.members] == [395, 396]
    assert all(m.role == HierarchyRole.SHASTIYA_KORMI.value for m in resp.members)
    assert all(m.summary is None for m in resp.members)


async def test_admin_user_id_am_depth_1_lists_sks_under_am(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM One", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "AM Two", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO Mine", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Other", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(395, "Mine SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Other SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=AM_ID,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
        depth=1,
    )

    assert resp.focus_user_id == AM_ID
    assert resp.summary.total_users == 1
    assert resp.total_members == 1
    assert resp.members[0].user_id == 395
    assert resp.members[0].role == HierarchyRole.SHASTIYA_KORMI.value
    assert resp.members[0].summary is None


async def test_illegal_depth_returns_422(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )

    with pytest.raises(AppError) as am_exc:
        await TeamActivityService(ch_client, session).get_team_activity(
            scope=_am_scope(AM_ID),
            focus_user_id=None,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=50,
            offset=0,
            tenant_id=None,
            depth=2,
        )
    assert am_exc.value.status == 422

    with pytest.raises(AppError) as po_exc:
        await TeamActivityService(ch_client, session).get_team_activity(
            scope=_po_scope(),
            focus_user_id=None,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=50,
            offset=0,
            tenant_id=None,
            depth=1,
        )
    assert po_exc.value.status == 422

    with pytest.raises(AppError) as sk_exc:
        await TeamActivityService(ch_client, session).get_team_activity(
            scope=_unrestricted_scope(),
            focus_user_id=395,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=50,
            offset=0,
            tenant_id=None,
            depth=1,
        )
    assert sk_exc.value.status == 422


async def test_depth_0_matches_default_admin_ams(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM Alpha", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "AM Beta", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)

    default_resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )
    depth0_resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
        depth=0,
    )

    assert [m.user_id for m in default_resp.members] == [m.user_id for m in depth0_resp.members]
    assert default_resp.total_members == depth0_resp.total_members
    assert default_resp.summary.total_users == depth0_resp.summary.total_users


async def test_sort_sk_name_desc(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)
    _stub_daily_rows(ch_client, [])

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
        sort_by="name",
        sort_dir="desc",
    )

    assert [m.user_id for m in resp.members] == [394, 395]


async def test_sort_sk_metric_flags_and_dir_reverse(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    family_id = uuid4()
    module_id = uuid4()
    _stub_assigned_modules_for_all_chws(monkeypatch, {module_id})
    completion = MagicMock()
    completion.chw_id = 395
    completion.module_family_id = family_id
    completion.latest_completed_module_id = module_id
    completion.completed_at = datetime(2026, 1, 15, tzinfo=UTC)
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleCompletionRepository.list_completed_in_range_for_chws",
        AsyncMock(return_value=[completion]),
    )
    mod = MagicMock()
    mod.id = module_id
    mod.module_family_id = family_id
    mod.title_localized = {"en": "Test Module"}
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleRepository.list_modules_by_ids",
        AsyncMock(return_value=[mod]),
    )
    _stub_daily_rows(
        ch_client,
        [
            {"chw_id": 395, "is_active": 1, "is_chatbot_engaged": 1, "chatbot_query_count": 3},
            {"chw_id": 394, "is_active": 0, "is_chatbot_engaged": 0, "chatbot_query_count": 0},
        ],
    )
    service = TeamActivityService(ch_client, session)
    kwargs = {
        "scope": _po_scope(),
        "focus_user_id": None,
        "from_date": date(2026, 1, 1),
        "to_date": date(2026, 1, 31),
        "limit": 50,
        "offset": 0,
        "tenant_id": None,
    }

    chatbot = await service.get_team_activity(sort_by="chatbot_engagement", sort_dir="asc", **kwargs)
    assert [m.user_id for m in chatbot.members] == [394, 395]
    chatbot_desc = await service.get_team_activity(sort_by="chatbot_engagement", sort_dir="desc", **kwargs)
    assert [m.user_id for m in chatbot_desc.members] == [395, 394]

    completion_asc = await service.get_team_activity(sort_by="module_completion", sort_dir="asc", **kwargs)
    assert [m.user_id for m in completion_asc.members] == [394, 395]
    completion_desc = await service.get_team_activity(sort_by="module_completion", sort_dir="desc", **kwargs)
    assert [m.user_id for m in completion_desc.members] == [395, 394]


async def test_sort_am_summary_counts_and_name_ties(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_am = 52
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM Charlie", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "AM Bravo", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(empty_am, "AM Alpha", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO Alpha", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Beta", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(395, "Active SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(501, "Idle SK A", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
            _org_user(502, "Idle SK B", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
        ],
    )
    _stub_assignments(monkeypatch)
    _stub_daily_rows(
        ch_client,
        [
            {"chw_id": 395, "is_active": 1, "is_chatbot_engaged": 1, "chatbot_query_count": 2},
            {"chw_id": 501, "is_active": 0, "is_chatbot_engaged": 0, "chatbot_query_count": 0},
            {"chw_id": 502, "is_active": 0, "is_chatbot_engaged": 0, "chatbot_query_count": 0},
        ],
    )
    service = TeamActivityService(ch_client, session)
    kwargs = {
        "scope": _unrestricted_scope(),
        "focus_user_id": None,
        "from_date": date(2026, 1, 1),
        "to_date": date(2026, 1, 31),
        "limit": 50,
        "offset": 0,
        "tenant_id": None,
    }

    by_name = await service.get_team_activity(**kwargs)
    assert [m.user_id for m in by_name.members] == [empty_am, OTHER_AM_ID, AM_ID]

    lowest_chat = await service.get_team_activity(sort_by="chatbot_engagement", **kwargs)
    assert [m.user_id for m in lowest_chat.members] == [empty_am, OTHER_AM_ID, AM_ID]
    assert lowest_chat.members[0].summary is not None
    assert lowest_chat.members[0].summary.users_chatbot_engaged == 0

    paged = await service.get_team_activity(
        sort_by="chatbot_engagement",
        limit=1,
        offset=0,
        **{k: v for k, v in kwargs.items() if k not in {"limit", "offset"}},
    )
    assert [m.user_id for m in paged.members] == [empty_am]
    assert paged.total_members == 3
    assert paged.total_pages == 3


async def test_sort_am_lowest_module_completion(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family_id = uuid4()
    module_id = uuid4()
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM Charlie", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "AM Bravo", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO Alpha", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Beta", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(395, "Done SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(501, "Open SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
        ],
    )
    _stub_assigned_modules_for_all_chws(monkeypatch, {module_id})
    completion = MagicMock()
    completion.chw_id = 395
    completion.module_family_id = family_id
    completion.latest_completed_module_id = module_id
    completion.completed_at = datetime(2026, 1, 15, tzinfo=UTC)
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleCompletionRepository.list_completed_in_range_for_chws",
        AsyncMock(return_value=[completion]),
    )
    mod = MagicMock()
    mod.id = module_id
    mod.module_family_id = family_id
    mod.title_localized = {"en": "Test Module"}
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleRepository.list_modules_by_ids",
        AsyncMock(return_value=[mod]),
    )
    _stub_daily_rows(ch_client, [])

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
        sort_by="module_completion",
    )

    assert [m.user_id for m in resp.members] == [OTHER_AM_ID, AM_ID]
    assert resp.members[0].summary is not None
    assert resp.members[0].summary.users_completed_module == 0
    assert resp.members[1].summary is not None
    assert resp.members[1].summary.users_completed_module == 1


def test_child_share_on_track_requires_strictly_more_than_sixty_percent() -> None:
    assert _child_share_on_track(0, 0) is False
    assert _child_share_on_track(3, 5) is False  # 60% is not > 0.60
    assert _child_share_on_track(2, 3) is True  # 66.6%


def test_build_performance_status_cascades_po_and_am() -> None:
    sk_ids_on_po = [701, 702, 703, 704]
    sk_off = 705
    po_on = 601
    po_off = 602
    am_id = 501
    empty_am = 502
    users = [
        _org_user(am_id, "AM", role=HierarchyRole.AREA_MANAGER.value),
        _org_user(empty_am, "AM Empty", role=HierarchyRole.AREA_MANAGER.value),
        _org_user(po_on, "PO On", role=HierarchyRole.PO.value, parent_id=am_id),
        _org_user(po_off, "PO Off", role=HierarchyRole.PO.value, parent_id=am_id),
        *[
            _org_user(
                sk_id,
                f"SK {sk_id}",
                role=HierarchyRole.SHASTIYA_KORMI.value,
                parent_id=po_on,
            )
            for sk_id in sk_ids_on_po
        ],
        _org_user(
            sk_off,
            "SK Off",
            role=HierarchyRole.SHASTIYA_KORMI.value,
            parent_id=po_off,
        ),
    ]
    by_id = {u.id: u for u in users}
    sk_on_track = {sk_id: True for sk_id in sk_ids_on_po[:3]}
    sk_on_track.update({sk_ids_on_po[3]: False, sk_off: False})
    status_by_id = _build_performance_status_by_user_id(by_id, sk_on_track=sk_on_track, geo_chw_ids=None)

    assert status_by_id[sk_ids_on_po[0]] == "on_track"
    assert status_by_id[sk_off] == "at_risk"
    assert status_by_id[po_on] == "on_track"
    assert status_by_id[po_off] == "at_risk"
    assert status_by_id[am_id] == "at_risk"
    assert status_by_id[empty_am] == "at_risk"


def test_build_performance_status_am_on_track_when_both_pos_on_track() -> None:
    am_id = 501
    po_a = 601
    po_b = 602
    sks_a = [701, 702]
    sks_b = [703, 704]
    users = [
        _org_user(am_id, "AM", role=HierarchyRole.AREA_MANAGER.value),
        _org_user(po_a, "PO A", role=HierarchyRole.PO.value, parent_id=am_id),
        _org_user(po_b, "PO B", role=HierarchyRole.PO.value, parent_id=am_id),
        *[
            _org_user(sk_id, f"SK {sk_id}", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=po_a)
            for sk_id in sks_a
        ],
        *[
            _org_user(sk_id, f"SK {sk_id}", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=po_b)
            for sk_id in sks_b
        ],
    ]
    by_id = {u.id: u for u in users}
    sk_on_track = {sk_id: True for sk_id in [*sks_a, *sks_b]}
    status_by_id = _build_performance_status_by_user_id(by_id, sk_on_track=sk_on_track, geo_chw_ids=None)

    assert status_by_id[po_a] == "on_track"
    assert status_by_id[po_b] == "on_track"
    assert status_by_id[am_id] == "on_track"


def test_sk_module_on_track_requires_at_least_sixty_percent() -> None:
    assigned_module_ids = {uuid4() for _ in range(10)}
    extra_unassigned = uuid4()
    assigned_list = list(assigned_module_ids)
    assert _sk_module_on_track(assigned_module_ids, set(assigned_list[:6])) is True  # 6/10 = 60%
    assert _sk_module_on_track(assigned_module_ids, set(assigned_list[:5])) is False  # 5/10
    assert _sk_module_on_track(assigned_module_ids, set(assigned_list[:5]) | {extra_unassigned}) is False
    assert _sk_module_on_track(assigned_module_ids, set(assigned_module_ids)) is True
    assert _sk_module_on_track(set(), set()) is False
    assert _sk_module_on_track(set(), {extra_unassigned}) is False


async def test_team_activity_sk_on_track_uses_responsive_assigned_module_ids(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assigned_module_ids = [uuid4() for _ in range(10)]
    responsive_module_ids = assigned_module_ids[:6]
    extra_unassigned = uuid4()
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments_by_chw(monkeypatch, {395: set(assigned_module_ids)})
    captured_query: dict[str, str] = {}

    async def query_side_effect(query: str, parameters: dict | None = None) -> list[dict]:
        _ = parameters
        if "SELECT DISTINCT" in query and "module_card_viewed" in query:
            captured_query["sql"] = query
            return [
                *[{"chw_id": 395, "module_id": str(module_id)} for module_id in responsive_module_ids],
                {"chw_id": 395, "module_id": str(extra_unassigned)},
                {"chw_id": 395, "module_id": "not-a-uuid"},
                {"chw_id": 395, "module_id": None},
            ]
        if "coaching_events" in query:
            return []
        if "last_chat_date" in query or "last_active_date" in query:
            return []
        if "chw_digital_help_daily" in query:
            return []
        if "chw_daily_summary" in query:
            return [{"chw_id": 395, "is_active": 1, "is_chatbot_engaged": 0, "chatbot_query_count": 0}]
        return []

    ch_client.query_rows = AsyncMock(side_effect=query_side_effect)

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert "module_card_viewed" in captured_query["sql"]
    assert "module_quiz_viewed" in captured_query["sql"]
    assert "module_quiz_attempted" in captured_query["sql"]
    assert resp.members[0].performance_status == "on_track"
    assert resp.members[0].has_completed_module_in_range is False


async def test_team_activity_unassigned_sk_is_at_risk(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments(monkeypatch)
    _stub_daily_rows(
        ch_client,
        [{"chw_id": 395, "is_active": 1, "is_chatbot_engaged": 1, "chatbot_query_count": 2}],
        responsive_rows=[{"chw_id": 395, "module_id": str(uuid4())}],
    )

    resp = await TeamActivityService(ch_client, session).get_team_activity(
        scope=_po_scope(),
        focus_user_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=50,
        offset=0,
        tenant_id=None,
    )

    assert resp.members[0].performance_status == "at_risk"


async def test_fetch_responsive_module_ids_skips_clickhouse_when_no_chws(
    ch_client: MagicMock,
    session: MagicMock,
) -> None:
    result = await TeamActivityService(ch_client, session)._fetch_responsive_module_ids(
        chw_ids=[],
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        tenant_id=None,
    )
    assert result == {}
    ch_client.query_rows.assert_not_called()


async def test_sort_sk_performance_status_puts_at_risk_first(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assigned_on = [uuid4() for _ in range(10)]
    assigned_off = [uuid4() for _ in range(10)]
    _patch_org_index(
        monkeypatch,
        [
            _org_user(ORGANIZER_ID, "PO", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(395, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(394, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
        ],
    )
    _stub_assignments_by_chw(monkeypatch, {395: set(assigned_on), 394: set(assigned_off)})
    _stub_daily_rows(
        ch_client,
        [],
        responsive_rows=[{"chw_id": 395, "module_id": str(module_id)} for module_id in assigned_on[:6]],
    )
    service = TeamActivityService(ch_client, session)
    kwargs = {
        "scope": _po_scope(),
        "focus_user_id": None,
        "from_date": date(2026, 1, 1),
        "to_date": date(2026, 1, 31),
        "limit": 50,
        "offset": 0,
        "tenant_id": None,
    }

    at_risk_first = await service.get_team_activity(sort_by="performance_status", sort_dir="asc", **kwargs)
    assert [m.user_id for m in at_risk_first.members] == [394, 395]
    assert [m.performance_status for m in at_risk_first.members] == ["at_risk", "on_track"]

    on_track_first = await service.get_team_activity(sort_by="performance_status", sort_dir="desc", **kwargs)
    assert [m.user_id for m in on_track_first.members] == [395, 394]


async def test_sort_am_performance_status_puts_at_risk_first(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    on_track_modules = [uuid4() for _ in range(10)]
    at_risk_module = uuid4()
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM Charlie", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(OTHER_AM_ID, "AM Bravo", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO On", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Off", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
            _org_user(395, "On SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=ORGANIZER_ID),
            _org_user(501, "Off SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
        ],
    )
    _stub_assignments_by_chw(
        monkeypatch,
        {395: set(on_track_modules), 501: {at_risk_module}},
    )
    _stub_daily_rows(
        ch_client,
        [],
        responsive_rows=[{"chw_id": 395, "module_id": str(module_id)} for module_id in on_track_modules[:6]],
    )
    service = TeamActivityService(ch_client, session)
    kwargs = {
        "scope": _unrestricted_scope(),
        "focus_user_id": None,
        "from_date": date(2026, 1, 1),
        "to_date": date(2026, 1, 31),
        "limit": 50,
        "offset": 0,
        "tenant_id": None,
    }

    at_risk_first = await service.get_team_activity(sort_by="performance_status", **kwargs)
    assert [m.user_id for m in at_risk_first.members] == [OTHER_AM_ID, AM_ID]
    assert [m.performance_status for m in at_risk_first.members] == ["at_risk", "on_track"]

    paged = await service.get_team_activity(
        sort_by="performance_status",
        limit=1,
        offset=0,
        **{k: v for k, v in kwargs.items() if k not in {"limit", "offset"}},
    )
    assert [m.user_id for m in paged.members] == [OTHER_AM_ID]
    assert paged.total_members == 2
    assert paged.total_pages == 2


async def test_team_activity_po_and_am_performance_status_cascade(
    ch_client: MagicMock,
    session: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    po_on_sks = [395, 396, 397, 398]
    po_off_sk = 501
    assigned_by_chw = {sk_id: {uuid4()} for sk_id in [*po_on_sks, po_off_sk]}
    _patch_org_index(
        monkeypatch,
        [
            _org_user(AM_ID, "AM One", role=HierarchyRole.AREA_MANAGER.value),
            _org_user(ORGANIZER_ID, "PO On", role=HierarchyRole.PO.value, parent_id=AM_ID),
            _org_user(OTHER_PO_ID, "PO Off", role=HierarchyRole.PO.value, parent_id=AM_ID),
            *[
                _org_user(
                    sk_id,
                    f"SK {sk_id}",
                    role=HierarchyRole.SHASTIYA_KORMI.value,
                    parent_id=ORGANIZER_ID,
                )
                for sk_id in po_on_sks
            ],
            _org_user(
                po_off_sk,
                "SK Off",
                role=HierarchyRole.SHASTIYA_KORMI.value,
                parent_id=OTHER_PO_ID,
            ),
        ],
    )
    _stub_assignments_by_chw(monkeypatch, assigned_by_chw)
    _stub_daily_rows(
        ch_client,
        [],
        responsive_rows=[
            {"chw_id": sk_id, "module_id": str(next(iter(assigned_by_chw[sk_id])))} for sk_id in po_on_sks[:3]
        ],
    )
    service = TeamActivityService(ch_client, session)
    kwargs = {
        "from_date": date(2026, 1, 1),
        "to_date": date(2026, 1, 31),
        "limit": 50,
        "offset": 0,
        "tenant_id": None,
    }

    am_resp = await service.get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=None,
        **kwargs,
    )
    assert am_resp.members[0].user_id == AM_ID
    assert am_resp.members[0].performance_status == "at_risk"

    po_resp = await service.get_team_activity(
        scope=_unrestricted_scope(),
        focus_user_id=AM_ID,
        **kwargs,
    )
    status_by_po = {member.user_id: member.performance_status for member in po_resp.members}
    assert status_by_po[ORGANIZER_ID] == "on_track"
    assert status_by_po[OTHER_PO_ID] == "at_risk"
