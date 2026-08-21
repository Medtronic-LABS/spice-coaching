"""Unit tests for PublishedModuleCompletionsService."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from mc_contracts.enums import HierarchyRole
from platform_service.auth.spice_identity import PublishedModuleCompletionsScope
from platform_service.services.dashboard_hierarchy import OrgUser
from platform_service.services.published_module_completions_service import (
    PublishedModuleCompletionsService,
)

AM_ID = 50
OTHER_AM_ID = 51
PO_ID = 401
OTHER_PO_ID = 999
SK_A = 395
SK_B = 394
SK_OTHER = 393
ORPHAN_SK = 392
TENANT_ID = 7


def _am_scope(viewer_id: int = AM_ID) -> PublishedModuleCompletionsScope:
    return PublishedModuleCompletionsScope(viewer_id=viewer_id, unrestricted=False)


def _unrestricted_scope(*, viewer_id: int | None = None) -> PublishedModuleCompletionsScope:
    return PublishedModuleCompletionsScope(viewer_id=viewer_id, unrestricted=True)


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


def _standard_org() -> list[OrgUser]:
    return [
        _org_user(AM_ID, "AM Alpha", role=HierarchyRole.AREA_MANAGER.value),
        _org_user(OTHER_AM_ID, "AM Beta", role=HierarchyRole.AREA_MANAGER.value),
        _org_user(PO_ID, "PO Alpha", role=HierarchyRole.PO.value, parent_id=AM_ID),
        _org_user(OTHER_PO_ID, "PO Beta", role=HierarchyRole.PO.value, parent_id=OTHER_AM_ID),
        _org_user(SK_A, "Alpha SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=PO_ID),
        _org_user(SK_B, "Alpha SK2", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=PO_ID),
        _org_user(SK_OTHER, "Beta SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=OTHER_PO_ID),
        _org_user(ORPHAN_SK, "Orphan SK", role=HierarchyRole.SHASTIYA_KORMI.value, parent_id=None),
    ]


def _patch_org_index(monkeypatch: pytest.MonkeyPatch, users: list[OrgUser]) -> None:
    index = {u.id: u for u in users}
    monkeypatch.setattr(
        "platform_service.services.published_module_completions_service.org_user_index",
        AsyncMock(return_value=index),
    )


def _module(
    *,
    module_id=None,
    family_id=None,
    published_at: datetime,
    title: dict[str, str] | None = None,
    chatbot_faqs_only: bool = False,
    lifecycle_status: str = "published",
) -> MagicMock:
    mod = MagicMock()
    mod.id = module_id or uuid4()
    mod.module_family_id = family_id or uuid4()
    mod.published_at = published_at
    mod.title_localized = title if title is not None else {"en": "Module"}
    mod.chatbot_faqs_only = chatbot_faqs_only
    mod.lifecycle_status = lifecycle_status
    return mod


def _completion(*, chw_id: int, family_id, completed_at: datetime) -> MagicMock:
    row = MagicMock()
    row.chw_id = chw_id
    row.module_family_id = family_id
    row.completed_at = completed_at
    return row


def _stub_repos(
    monkeypatch: pytest.MonkeyPatch,
    *,
    modules: list[MagicMock],
    total_modules: int | None = None,
    completions: list[MagicMock] | None = None,
    assignments: list[tuple[UUID, int]] | None = None,
) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    count_mock = AsyncMock(return_value=total_modules if total_modules is not None else len(modules))
    list_mock = AsyncMock(return_value=modules)
    completions_mock = AsyncMock(return_value=completions or [])
    assignments_mock = AsyncMock(return_value=assignments or [])

    monkeypatch.setattr(
        "platform_service.services.published_module_completions_service.ModuleRepository.count_modules",
        count_mock,
    )
    monkeypatch.setattr(
        "platform_service.services.published_module_completions_service.ModuleRepository.list_modules",
        list_mock,
    )
    monkeypatch.setattr(
        "platform_service.services.published_module_completions_service"
        ".ModuleCompletionRepository.list_completed_in_range_for_chws",
        completions_mock,
    )
    monkeypatch.setattr(
        "platform_service.services.published_module_completions_service"
        ".ModuleAssignmentRepository.list_assignments_for_families_and_chws",
        assignments_mock,
    )
    return count_mock, list_mock, completions_mock


@pytest.mark.asyncio
async def test_admin_counts_all_tree_sks_excludes_orphans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family = uuid4()
    published = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    mod = _module(family_id=family, published_at=published, title={"en": "M1"})
    _patch_org_index(monkeypatch, _standard_org())
    count_mock, list_mock, completions_mock = _stub_repos(
        monkeypatch,
        modules=[mod],
        completions=[
            _completion(chw_id=SK_A, family_id=family, completed_at=datetime(2026, 1, 20, tzinfo=UTC)),
            _completion(chw_id=SK_OTHER, family_id=family, completed_at=datetime(2026, 1, 21, tzinfo=UTC)),
            _completion(chw_id=ORPHAN_SK, family_id=family, completed_at=datetime(2026, 1, 22, tzinfo=UTC)),
        ],
    )

    resp = await PublishedModuleCompletionsService(MagicMock()).get_published_module_completions(
        scope=_unrestricted_scope(),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=20,
        offset=0,
        tenant_id=TENANT_ID,
    )

    assert resp.total_descendant_sk_count == 3  # SK_A, SK_B, SK_OTHER — orphan excluded
    assert resp.total_modules == 1
    assert len(resp.modules) == 1
    item = resp.modules[0]
    assert item.module_id == mod.id
    assert item.module_family_id == family
    assert item.title == {"en": "M1"}
    assert item.completed_sk_count == 2  # orphan not in visible set / not passed chw_ids
    assert item.total_descendant_sk_count == 3

    list_kwargs = list_mock.await_args.kwargs
    assert list_kwargs["status"] == "published"
    assert list_kwargs["chatbot_faqs_only"] is False
    assert list_kwargs["sort_by"] == "published_at"
    assert list_kwargs["sort_dir"] == "desc"
    assert list_kwargs["tenant_id"] == TENANT_ID
    assert count_mock.await_args.kwargs["chatbot_faqs_only"] is False
    assert set(completions_mock.await_args.kwargs["chw_ids"]) == {SK_A, SK_B, SK_OTHER}


@pytest.mark.asyncio
async def test_am_scoped_to_descendant_sks_only(monkeypatch: pytest.MonkeyPatch) -> None:
    family = uuid4()
    mod = _module(family_id=family, published_at=datetime(2026, 1, 10, tzinfo=UTC), title={"en": "Scoped"})
    _patch_org_index(monkeypatch, _standard_org())
    _, _, completions_mock = _stub_repos(
        monkeypatch,
        modules=[mod],
        completions=[
            _completion(chw_id=SK_A, family_id=family, completed_at=datetime(2026, 1, 12, tzinfo=UTC)),
            _completion(chw_id=SK_OTHER, family_id=family, completed_at=datetime(2026, 1, 12, tzinfo=UTC)),
        ],
    )

    resp = await PublishedModuleCompletionsService(MagicMock()).get_published_module_completions(
        scope=_am_scope(AM_ID),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=20,
        offset=0,
        tenant_id=TENANT_ID,
    )

    assert resp.total_descendant_sk_count == 2  # SK_A, SK_B under AM
    assert resp.modules[0].completed_sk_count == 1
    assert set(completions_mock.await_args.kwargs["chw_ids"]) == {SK_A, SK_B}


@pytest.mark.asyncio
async def test_zero_completion_modules_included(monkeypatch: pytest.MonkeyPatch) -> None:
    family = uuid4()
    mod = _module(family_id=family, published_at=datetime(2026, 1, 5, tzinfo=UTC))
    _patch_org_index(monkeypatch, _standard_org())
    _stub_repos(monkeypatch, modules=[mod], completions=[])

    resp = await PublishedModuleCompletionsService(MagicMock()).get_published_module_completions(
        scope=_am_scope(),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=20,
        offset=0,
        tenant_id=TENANT_ID,
    )

    assert resp.modules[0].completed_sk_count == 0
    assert resp.modules[0].total_descendant_sk_count == 2


@pytest.mark.asyncio
async def test_two_versions_same_family_share_completed_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family = uuid4()
    m1 = _module(
        module_id=uuid4(),
        family_id=family,
        published_at=datetime(2026, 1, 20, tzinfo=UTC),
        title={"en": "v2"},
    )
    m2 = _module(
        module_id=uuid4(),
        family_id=family,
        published_at=datetime(2026, 1, 10, tzinfo=UTC),
        title={"en": "v1"},
    )
    _patch_org_index(monkeypatch, _standard_org())
    _stub_repos(
        monkeypatch,
        modules=[m1, m2],
        total_modules=2,
        completions=[
            _completion(chw_id=SK_A, family_id=family, completed_at=datetime(2026, 1, 15, tzinfo=UTC)),
            _completion(chw_id=SK_B, family_id=family, completed_at=datetime(2026, 1, 16, tzinfo=UTC)),
        ],
    )

    resp = await PublishedModuleCompletionsService(MagicMock()).get_published_module_completions(
        scope=_am_scope(),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=20,
        offset=0,
        tenant_id=TENANT_ID,
    )

    assert len(resp.modules) == 2
    assert resp.modules[0].completed_sk_count == 2
    assert resp.modules[1].completed_sk_count == 2
    assert resp.modules[0].module_id != resp.modules[1].module_id


@pytest.mark.asyncio
async def test_empty_sk_set_skips_completion_query(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _module(published_at=datetime(2026, 1, 5, tzinfo=UTC))
    _patch_org_index(
        monkeypatch,
        [_org_user(AM_ID, "AM alone", role=HierarchyRole.AREA_MANAGER.value)],
    )
    _, _, completions_mock = _stub_repos(monkeypatch, modules=[mod], completions=[])

    resp = await PublishedModuleCompletionsService(MagicMock()).get_published_module_completions(
        scope=_am_scope(AM_ID),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=20,
        offset=0,
        tenant_id=TENANT_ID,
    )

    assert resp.total_descendant_sk_count == 0
    assert resp.modules[0].completed_sk_count == 0
    completions_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_pagination_passed_to_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_org_index(monkeypatch, _standard_org())
    count_mock, list_mock, _ = _stub_repos(monkeypatch, modules=[], total_modules=42)

    resp = await PublishedModuleCompletionsService(MagicMock()).get_published_module_completions(
        scope=_unrestricted_scope(),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=10,
        offset=20,
        tenant_id=TENANT_ID,
    )

    assert resp.total_modules == 42
    assert resp.limit == 10
    assert resp.offset == 20
    assert resp.modules == []
    assert list_mock.await_args.kwargs["limit"] == 10
    assert list_mock.await_args.kwargs["offset"] == 20
    assert count_mock.await_args.kwargs["tenant_id"] == TENANT_ID


@pytest.mark.asyncio
async def test_geo_filter_narrows_visible_sks(monkeypatch: pytest.MonkeyPatch) -> None:
    family = uuid4()
    mod = _module(family_id=family, published_at=datetime(2026, 1, 10, tzinfo=UTC))
    _patch_org_index(monkeypatch, _standard_org())
    _, _, completions_mock = _stub_repos(
        monkeypatch,
        modules=[mod],
        completions=[
            _completion(chw_id=SK_A, family_id=family, completed_at=datetime(2026, 1, 12, tzinfo=UTC)),
            _completion(chw_id=SK_B, family_id=family, completed_at=datetime(2026, 1, 12, tzinfo=UTC)),
        ],
    )

    resp = await PublishedModuleCompletionsService(MagicMock()).get_published_module_completions(
        scope=_am_scope(AM_ID),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=20,
        offset=0,
        tenant_id=TENANT_ID,
        geo_chw_ids=frozenset({SK_A}),
    )

    assert resp.total_descendant_sk_count == 1
    assert resp.modules[0].completed_sk_count == 1
    assert completions_mock.await_args.kwargs["chw_ids"] == [SK_A]


@pytest.mark.asyncio
async def test_assigned_sk_count_scoped_to_visible_sks(monkeypatch: pytest.MonkeyPatch) -> None:
    family = uuid4()
    mod = _module(family_id=family, published_at=datetime(2026, 1, 10, tzinfo=UTC))
    _patch_org_index(monkeypatch, _standard_org())
    _stub_repos(
        monkeypatch,
        modules=[mod],
        completions=[],
        assignments=[(family, SK_A), (family, SK_OTHER)],
    )

    resp = await PublishedModuleCompletionsService(MagicMock()).get_published_module_completions(
        scope=_am_scope(AM_ID),
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        limit=20,
        offset=0,
        tenant_id=TENANT_ID,
    )

    # Under AM_ID, visible SKs are {SK_A, SK_B}. SK_OTHER is excluded because it's not under AM_ID.
    assert resp.total_descendant_sk_count == 2
    assert resp.modules[0].assigned_sk_count == 1
