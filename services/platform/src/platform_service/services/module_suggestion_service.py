"""Gap-driven module suggestions for a CHW (W-8 adjacent).

Resolves published modules from `chw_behavioural_gap_state` via
`module.primary_gap_id`, with tenant scoping and a fallback to the most
recently created published modules per family when the gap-driven list is
empty.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.behavioural_gap import BehaviouralGap
from platform_service.db.models.chw_behavioural_gap_state import CHWBehaviouralGapState
from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.repositories.module_repository import ModuleRepository

_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}


def _gap_state_sort_key(state: CHWBehaviouralGapState) -> tuple[int, int, float]:
    sev = _SEVERITY_RANK.get(state.severity_current, 99)
    last = float("inf") if state.last_observed_at is None else -state.last_observed_at.timestamp()
    return (sev, -state.occurrence_count, last)


@dataclass(frozen=True)
class ModuleSuggestionItem:
    module_id: UUID
    module_family_id: UUID
    source: Literal["gap", "fallback"]
    behavioural_gap_id: UUID | None = None


class ModuleSuggestionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._modules = ModuleRepository(session)

    async def suggest_for_chw(
        self,
        *,
        chw_id: int,
        tenant_id: UUID,
    ) -> list[ModuleSuggestionItem]:
        states = await self._load_relevant_gap_states(chw_id=chw_id, tenant_id=tenant_id)
        sorted_states = sorted(states, key=_gap_state_sort_key)
        gap_ids = [s.behavioural_gap_id for s in sorted_states]

        if not gap_ids:
            return await self._fallback_items(tenant_id=tenant_id)

        modules_raw = await self._modules.list_published_modules_for_primary_gap_ids(
            gap_ids=gap_ids,
            tenant_id=tenant_id,
        )
        if not modules_raw:
            return await self._fallback_items(tenant_id=tenant_id)

        family_ids = {m.module_family_id for m in modules_raw}
        fam_result = await self._session.execute(select(ModuleFamily).where(ModuleFamily.id.in_(family_ids)))
        families = {f.id: f for f in fam_result.scalars().all()}

        canonical_by_family = _canonical_modules_by_family(
            modules_raw,
            families,
        )
        by_gap = _group_canonical_by_gap(canonical_by_family.values())

        used_families: set[UUID] = set()
        picked: list[tuple[Module, UUID]] = []

        for state in sorted_states:
            if len(picked) >= 5:
                break
            gid = state.behavioural_gap_id
            cands = by_gap.get(gid, [])
            cands_sorted = sorted(
                cands,
                key=lambda m: m.created_at.timestamp(),
                reverse=True,
            )
            for mod in cands_sorted:
                if mod.module_family_id in used_families:
                    continue
                picked.append((mod, gid))
                used_families.add(mod.module_family_id)
                break

        if not picked:
            return await self._fallback_items(tenant_id=tenant_id)

        return [
            ModuleSuggestionItem(
                module_id=m.id,
                module_family_id=m.module_family_id,
                source="gap",
                behavioural_gap_id=gid,
            )
            for m, gid in picked
        ]

    async def _load_relevant_gap_states(
        self,
        *,
        chw_id: int,
        tenant_id: UUID,
    ) -> list[CHWBehaviouralGapState]:
        stmt = (
            select(CHWBehaviouralGapState)
            .join(BehaviouralGap, BehaviouralGap.id == CHWBehaviouralGapState.behavioural_gap_id)
            .where(
                CHWBehaviouralGapState.chw_id == chw_id,
                or_(
                    CHWBehaviouralGapState.tenant_id.is_(None),
                    CHWBehaviouralGapState.tenant_id == tenant_id,
                ),
                CHWBehaviouralGapState.status.in_(("active", "monitoring")),
                BehaviouralGap.status == "active",
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _fallback_items(self, *, tenant_id: UUID) -> list[ModuleSuggestionItem]:
        rows = await self._modules.list_recent_published_one_per_family(
            tenant_id=tenant_id,
            limit=5,
        )
        return [
            ModuleSuggestionItem(
                module_id=m.id,
                module_family_id=m.module_family_id,
                source="fallback",
                behavioural_gap_id=None,
            )
            for m in rows
        ]


def _canonical_modules_by_family(
    modules_raw: list[Module],
    families: dict[UUID, ModuleFamily],
) -> dict[UUID, Module]:
    """Pick one published row per family: prefer `current_published_module_id`
    when it appears in candidates, else highest `version`."""
    by_family: dict[UUID, list[Module]] = defaultdict(list)
    for m in modules_raw:
        by_family[m.module_family_id].append(m)

    out: dict[UUID, Module] = {}
    for family_id, cands in by_family.items():
        fam = families.get(family_id)
        if fam is not None and fam.current_published_module_id is not None:
            for m in cands:
                if m.id == fam.current_published_module_id:
                    out[family_id] = m
                    break
            else:
                out[family_id] = max(cands, key=lambda m: m.version)
        else:
            out[family_id] = max(cands, key=lambda m: m.version)
    return out


def _group_canonical_by_gap(modules: Iterable[Module]) -> dict[UUID, list[Module]]:
    by_gap: dict[UUID, list[Module]] = defaultdict(list)
    for m in modules:
        if m.primary_gap_id is not None:
            by_gap[m.primary_gap_id].append(m)
    return by_gap
