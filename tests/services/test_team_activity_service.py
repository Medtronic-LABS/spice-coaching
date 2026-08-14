"""Unit tests for TeamActivityService."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

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
    _count_refreshers,
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
    )


def _stub_assignments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.resolve_assigned_module_ids",
        AsyncMock(return_value=set()),
    )
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.ModuleCompletionRepository.list_completed_in_range_for_chws",
        AsyncMock(return_value=[]),
    )


@pytest.fixture
def ch_client() -> MagicMock:
    client = MagicMock()
    client.query_rows = AsyncMock(return_value=[])
    return client


@pytest.fixture
def session() -> MagicMock:
    return MagicMock()


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
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.resolve_assigned_module_ids",
        AsyncMock(return_value={module_id}),
    )

    completion = MagicMock()
    completion.chw_id = 395
    completion.module_family_id = family_id
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
    last_asked = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

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
                "last_asked_at": datetime(2026, 1, 10, 8, 0, tzinfo=UTC),
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
