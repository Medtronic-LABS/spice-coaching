"""Stage 2 module-drafter repository.

Persists Stage 2 output: a Module row with cards inlined as a JSON array on
`module_json` (per `docs/ARCHITECTURE_RESET.md`). The Module is created
auto-published (`lifecycle_status='published'`, `clinically_reviewed=false`)
and the orchestrator enqueues post-publish embedding + quiz workers.

Quiz questions are written by the post-publish quiz worker, not here — quiz
generation runs on the published module asynchronously and writes
`module_quiz_question` rows linked via the new `module_id` FK.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import get_settings
from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily


def _slugify(text: str) -> str:
    """Crude slug for module_code derivation. Bangla survives via raw chars."""
    cleaned = re.sub(r"\s+", "-", (text or "").strip().lower())
    cleaned = re.sub(r"[^\w\-]+", "", cleaned, flags=re.UNICODE)
    return cleaned[:80] or "module"


class ModuleDrafterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_module_family(
        self, *, proposed_title: str, created_by: UUID | None = None
    ) -> ModuleFamily:
        """Look up by derived module_code; create if absent.

        On collision we append a numeric suffix (-1, -2, …) so two modules
        with the same proposed_title still get distinct families. Module
        re-versioning (same family, version+1) goes through the dashboard's
        edit endpoint, not through here.
        """
        slug = _slugify(proposed_title)
        candidate_code = slug
        attempt = 0
        while True:
            existing = await self._session.execute(
                select(ModuleFamily).where(ModuleFamily.module_code == candidate_code)
            )
            row = existing.scalar_one_or_none()
            if row is None:
                fam = ModuleFamily(module_code=candidate_code, created_by=created_by)
                self._session.add(fam)
                await self._session.flush()
                return fam
            attempt += 1
            candidate_code = f"{slug}-{attempt}"

    async def create_published_module(
        self,
        *,
        family: ModuleFamily,
        candidate: dict[str, Any],
        cards: list[dict[str, Any]],
        source_document_ids: list[UUID],
        primary_gap_id: UUID | None = None,
        quality_flags: dict[str, Any] | None = None,
    ) -> Module:
        """Persist a Module row with cards inlined as `module_json.cards`.

        Auto-publish path: status goes to `published` and `clinically_reviewed`
        defaults to false. The admin dashboard flips that flag once a
        clinician has signed off — it is not a publish gate.

        `quality_flags` carries the advisory flags the candidate accumulated
        in Stage 2 (insufficient-source heuristic) plus any Stage 2-draft
        validator soft-warning summary. Pipeline never gates on these.
        """
        version = await self._next_version(family.id)
        # Strip per-card transient fields the LLM included for downstream
        # use (e.g., `card_family_id`, `field_flags`) but normalise their
        # keys so the runtime payload is stable.
        cards_payload = [_normalise_card(c) for c in cards]
        module_json: dict[str, Any] = {"cards": cards_payload}
        now = datetime.now(UTC)

        # Title resolution. The Stage 2 candidate's `proposed_title` is in
        # English (the consolidator prompt outputs in English). Cards have
        # proper bilingual titles per the Stage 2-draft prompt schema.
        # Compose:
        #   - title_en = candidate's proposed_title (English from Stage 2)
        #   - title_bn = first card's title_bn (Bangla from Stage 2-draft).
        # Fallback to candidate.proposed_title in BOTH slots when cards
        # somehow lack a Bangla title — better than empty.
        proposed_title = candidate.get("proposed_title", "") or ""
        first_card_title_bn = ""
        for c in cards_payload:
            t = (c.get("title_bn") or "").strip()
            if t:
                first_card_title_bn = t
                break
        title_en = proposed_title.strip()
        title_bn = first_card_title_bn or title_en
        # Hard-fail when both are empty: a module without any title is
        # un-renderable. Caller (Stage 2-draft) catches this and skips
        # the candidate rather than persisting a faceless module row.
        if not title_bn and not title_en:
            raise ValueError(
                f"create_published_module: candidate has no usable title "
                f"(proposed_title={proposed_title!r}, "
                f"cards={len(cards_payload)} with no title_bn)"
            )
        # Hard-fail on missing English title for module types that are
        # discoverable by English-language content admins. `content_update`
        # is Bangla-primary (supervisor updates); the others ship to the
        # admin dashboard where reviewers work in English.
        _module_type = candidate.get("proposed_module_type", "refresher")
        _requires_title_en = _module_type in {"initial_training", "refresher", "digital_proficiency"}
        if _requires_title_en and not title_en:
            raise ValueError(
                f"create_published_module: module_type={_module_type!r} requires "
                f"a non-empty title_en but proposed_title is empty. "
                f"The consolidation prompt must emit English proposed_title values; "
                f"check Stage 2 consolidation output for this candidate."
            )

        module = Module(
            module_family_id=family.id,
            version=version,
            title_bn=title_bn,
            title_en=title_en or None,
            description_bn=candidate.get("scope_summary"),
            domain=candidate.get("domain") or get_settings().default_module_domain,
            sub_domain=candidate.get("sub_domain"),
            module_type=candidate.get("proposed_module_type", "refresher"),
            primary_gap_id=primary_gap_id,
            estimated_minutes=int(candidate.get("estimated_minutes", 10)),
            difficulty_level=candidate.get("difficulty_level", "moderate"),
            source_document_ids=list(source_document_ids),
            module_json=module_json,
            quality_flags_jsonb=quality_flags,
            lifecycle_status="draft",
            clinically_reviewed=False,
            published_at=None,
        )
        self._session.add(module)
        await self._session.flush()

        # Do not update family.current_published_module_id for drafts.
        # It will be updated when the module is published.

        return module

    # Backwards-compat alias for any caller still on the old name. New code
    # should call `create_published_module` directly.
    create_draft_module = create_published_module

    async def _next_version(self, module_family_id: UUID) -> int:
        result = await self._session.execute(
            select(Module.version)
            .where(Module.module_family_id == module_family_id)
            .order_by(Module.version.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return (row or 0) + 1


def _normalise_card(card: dict[str, Any]) -> dict[str, Any]:
    """Project the drafter card dict into the runtime payload shape.

    Drops non-runtime fields (e.g., `card_family_id`, `figure_ref_block_id`,
    `field_flags`) and keeps the bilingual content + structured metadata
    that the mobile app and admin dashboard render. Position in the cards
    array is the card's identity — there are no stable card IDs.
    """
    runtime_keys = (
        "title_bn",
        "title_en",
        "body_bn",
        "body_en",
        "previous_practice_bn",
        "previous_practice_en",
        "current_practice_bn",
        "current_practice_en",
        "rationale_for_change_bn",
        "rationale_for_change_en",
        "next_action_bn",
        "next_action_en",
        "thresholds",
        "source_block_ids",
        "figure_ref_block_id",
    )
    return {k: card[k] for k in runtime_keys if k in card and card[k] is not None}
