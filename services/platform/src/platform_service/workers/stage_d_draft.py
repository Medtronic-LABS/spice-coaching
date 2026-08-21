"""Stage 2-draft (was Stage D) — locale-keyed card drafter, per candidate.

Per `docs/ARCHITECTURE_RESET.md`:

- Stage 2-draft takes one `module_candidate_draft`, drafts cards in the
  deployment primary locale, and persists a `module` row as
  `lifecycle_status='draft'` with cards populated.
- When a semantically similar **active** module exists (the highest-version
  published if the family has one, otherwise the highest-version draft;
  older iterations in the same family are ignored), an LLM merges the old
  and new card sets
  (new wins on conflict). Stage D then persists a dual path in **two new**
  families (matched tip family untouched): secondary = LLM-merged cards
  (v1 in its family), primary = current-document cards (v1 in its family),
  both as `review_pending`, linked to each other and the matched tip.
- Quiz and gap-classification are separate post-publish Celery workers; this
  stage enqueues them via ``DraftPipeline.enqueue_post_publish`` once module
  rows have been committed. Card/module search metadata and embeddings run
  synchronously at admin publish (see ``module_publish_enrichment``): when
  ``publish_enrichment_parallel_metadata_enabled`` is on, card and module
  search-metadata LLM calls run concurrently, then embedding.
- `module_card_validator` runs on each drafted card; cards with hard
  violations are dropped, soft warnings are annotated as `field_flags`.
- If the validator strips the module below `card_min_count`, the candidate
  is skipped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.tenant_context import require_selected_tenant_id
from platform_service.config import Settings, get_settings
from platform_service.db.models.module import Module
from platform_service.db.models.module_candidate_draft import ModuleCandidateDraft
from platform_service.db.repositories.module_candidate_repository import (
    ModuleCandidateRepository,
)
from platform_service.db.repositories.module_drafter_repository import (
    ModuleDrafterRepository,
)
from platform_service.db.repositories.module_repository import ModuleRepository
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.localized import deployment_locales, primary_text
from platform_service.services.card_drafter import CardDrafter
from platform_service.services.card_image_assigner import embed_images_in_body_localized
from platform_service.services.card_normalisation import card_row_to_dict
from platform_service.services.draft_pipeline import DraftPipeline
from platform_service.services.ingestion_cardinality import resolve_for_candidate
from platform_service.services.published_module_merger import (
    PublishedModuleMerger,
    PublishedModuleMergerError,
    published_module_to_merge_dict,
)
from platform_service.services.run_state_service import RunStateService

logger = logging.getLogger(__name__)


def _embed_tiptap_for_cards(cards: list[dict[str, Any]], *, settings: Settings) -> list[dict[str, Any]]:
    """Embed TipTap image nodes into body_localized for each card that has media."""
    bucket = settings.object_storage_bucket_name
    primary_locale = deployment_locales(settings)
    result: list[dict[str, Any]] = []
    for card in cards:
        media: list[dict[str, Any]] = card.get("media") or []
        if not media:
            result.append(card)
            continue
        updated_body = embed_images_in_body_localized(
            card.get("body") if isinstance(card.get("body"), dict) else None,
            media_items=media,
            primary_locale=primary_locale,
            bucket_name=bucket,
        )
        result.append({**card, "body": updated_body})
    return result


def _strip_media_from_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return cards without the 'media' key (for sending to merger LLM)."""
    return [{k: v for k, v in card.items() if k != "media"} for card in cards]


def _preserve_card_media(
    merged_cards: list[dict[str, Any]],
    *,
    source_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Copy 'media' from the best-matching source card onto each merged card.

    Uses the same block-id overlap heuristic as the rich-body preservor.
    If no match is found, the merged card is returned unchanged (no media).
    """

    def _block_ids(card: dict[str, Any]) -> set[str]:
        ids: set[str] = set()
        for raw in card.get("source_block_ids") or []:
            if raw:
                ids.add(str(raw).strip().lower())
        return ids

    result: list[dict[str, Any]] = []
    for merged in merged_cards:
        merged_blocks = _block_ids(merged)
        best: dict[str, Any] | None = None
        best_overlap = 0
        for src in source_cards:
            src_blocks = _block_ids(src)
            overlap = len(merged_blocks & src_blocks)
            if overlap > best_overlap:
                best_overlap = overlap
                best = src
        if best is not None and best.get("media"):
            result.append({**merged, "media": best["media"]})
        else:
            result.append(merged)
    return result


@dataclass(frozen=True)
class StageDResult:
    """Outcome of Stage 2-draft for one candidate."""

    candidate_id: UUID
    module_id: UUID | None
    cards_count: int
    # Quiz is generated by a separate post-publish worker; Stage 2-draft
    # always returns 0 here. The pipeline_orchestrator will enqueue the
    # quiz worker on a non-None module_id.
    questions_count: int
    insufficient_reason: str | None
    merged_from_module_id: UUID | None = None
    was_published_merge: bool = False
    secondary_module_id: UUID | None = None


@dataclass(frozen=True)
class MergeProposal:
    """LLM merge proposal used immediately for dual-path persistence."""

    matched_module_id: UUID
    match_rationale: str | None
    proposed_title: str | None
    new_cards: list[dict[str, Any]]
    merged_cards: list[dict[str, Any]]


class StageDOrchestrator:
    def __init__(
        self,
        session: AsyncSession,
        *,
        card_drafter: CardDrafter | None = None,
        published_module_merger: PublishedModuleMerger | None = None,
        draft_pipeline: DraftPipeline | None = None,
        # Quiz / distractor-critique kwargs accepted for backwards-compat
        # with callers that still pass them; ignored here. Quiz generation
        # is now a post-publish Celery worker.
        quiz_drafter: object = None,
        distractor_critique: object = None,
    ) -> None:
        self._session = session
        self._candidate_repo = ModuleCandidateRepository(session)
        self._drafter_repo = ModuleDrafterRepository(session)
        self._module_repo = ModuleRepository(session)
        self._published_merger = published_module_merger or PublishedModuleMerger()
        self._pipeline = draft_pipeline or DraftPipeline(session, card_drafter=card_drafter)
        # Silence the unused-arg warnings without keeping references.
        del quiz_drafter, distractor_critique

    async def run(
        self,
        *,
        candidate_id: UUID,
        enqueue_post_publish: bool = True,
        skip_merge: bool = False,
        step_id: UUID | None = None,
    ) -> StageDResult:
        """Execute Stage 2-draft for one candidate.

        `enqueue_post_publish` controls whether quiz + embedding generation
        Celery tasks are fired after the module is persisted. Default True
        preserves the existing per-doc ingestion flow. The cross-source
        fusion runner passes False because it may DELETE a freshly-drafted
        module on cross-source coverage failure, which races with the
        post-publish workers and produces FK violations on insert. The
        runner re-enqueues after coverage validation passes.

        `skip_merge` when True skips merging new cards into similar
        active modules (internal opt-out used by cross-source fusion).

        When merge is attempted and the LLM finds a match, dual-path
        ``review_pending`` modules are persisted immediately in two new
        families (no parking; matched tip family untouched).
        """
        candidate = await self._candidate_repo.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError(f"module_candidate_draft {candidate_id} not found")

        candidate_dict = self._candidate_to_dict(candidate)
        cited_blocks, valid_block_ids = await self._pipeline.load_cited_blocks(candidate_dict)

        draft_outcome = await self._pipeline.draft_and_validate_cards(
            candidate_id=candidate_id,
            candidate_dict=candidate_dict,
            cited_blocks=cited_blocks,
            valid_block_ids=valid_block_ids,
        )
        if draft_outcome.insufficient_reason is not None:
            return StageDResult(
                candidate_id=candidate_id,
                module_id=None,
                cards_count=0,
                questions_count=0,
                insufficient_reason=draft_outcome.insufficient_reason,
            )
        cards = draft_outcome.cards or []

        source_document_ids = self._pipeline.extract_source_document_ids(candidate_dict)
        if not skip_merge:
            if step_id is not None:
                run_state = RunStateService(self._session)
                await run_state.patch_step_input_summary(
                    step_id,
                    {
                        "activity": "published_module_merge",
                        "candidate_id": str(candidate_id),
                    },
                )
                await self._session.commit()
            proposal = await self._propose_published_merge(
                candidate_id=candidate_id,
                candidate_dict=candidate_dict,
                cards=cards,
                valid_block_ids=valid_block_ids,
            )
            if proposal is not None:
                return await self._persist_dual_path_merge(
                    candidate=candidate,
                    candidate_dict=candidate_dict,
                    proposal=proposal,
                    enqueue_post_publish=enqueue_post_publish,
                )

        return await self._persist_new_module(
            candidate=candidate,
            candidate_dict=candidate_dict,
            cards=cards,
            source_document_ids=source_document_ids,
            enqueue_post_publish=enqueue_post_publish,
        )

    async def _persist_new_module(
        self,
        *,
        candidate: ModuleCandidateDraft,
        candidate_dict: dict[str, Any],
        cards: list[dict[str, Any]],
        source_document_ids: list[UUID],
        enqueue_post_publish: bool,
    ) -> StageDResult:
        tenant_id = await self._resolve_ingest_tenant_id(source_document_ids)
        created_by_user_id = await self._resolve_created_by_from_sources(source_document_ids)
        family = await self._drafter_repo.get_or_create_module_family(
            proposed_title=candidate_dict.get("proposed_title", "Untitled Module"),
            tenant_id=tenant_id,
        )
        cards = _embed_tiptap_for_cards(cards, settings=get_settings())
        module = await self._drafter_repo.create_published_module(
            family=family,
            candidate=candidate_dict,
            cards=cards,
            source_document_ids=source_document_ids,
            quality_flags=candidate.quality_flags_jsonb,
            created_by_user_id=created_by_user_id,
            ingestion_run_id=candidate.ingestion_run_id,
        )
        await self._session.flush()
        if enqueue_post_publish:
            await self._enqueue_post_publish(
                module.id,
                source_document_ids,
                ingestion_run_id=candidate.ingestion_run_id,
                candidate_id=candidate.id,
            )
        return StageDResult(
            candidate_id=candidate.id,
            module_id=module.id,
            cards_count=len(cards),
            questions_count=0,
            insufficient_reason=None,
        )

    async def _resolve_ingest_tenant_id(self, source_document_ids: list[UUID]) -> int:
        """Bound selected tenant, consistent with source documents; fail hard on mismatch."""
        tenant_id = require_selected_tenant_id()
        if not source_document_ids:
            raise ValueError("Stage D cannot create a module without source_document_ids")
        docs = await SourceRepository(self._session).list_source_documents_by_ids(source_document_ids)
        found_ids = {doc.id for doc in docs}
        missing = [doc_id for doc_id in source_document_ids if doc_id not in found_ids]
        if missing:
            raise ValueError(f"source_document(s) not found for Stage D tenant resolution: {missing}")
        tenants = {doc.tenant_id for doc in docs}
        if len(tenants) != 1:
            raise ValueError(
                f"source documents span multiple tenants {sorted(tenants)}; cannot stamp module family"
            )
        source_tenant_id = tenants.pop()
        if source_tenant_id != tenant_id:
            raise ValueError(
                f"source document tenant_id={source_tenant_id} does not match "
                f"selected ingest tenant_id={tenant_id}"
            )
        return tenant_id

    async def _resolve_created_by_from_sources(self, source_document_ids: list[UUID]) -> int | None:
        """Attribute pipeline-created modules to the first linked doc uploader."""
        if not source_document_ids:
            return None
        docs = await SourceRepository(self._session).list_source_documents_by_ids(source_document_ids)
        docs_by_id = {doc.id: doc for doc in docs}
        for doc_id in source_document_ids:
            doc = docs_by_id.get(doc_id)
            if doc is not None and doc.uploaded_by is not None:
                return doc.uploaded_by
        return None

    async def _persist_dual_path_merge(
        self,
        *,
        candidate: ModuleCandidateDraft,
        candidate_dict: dict[str, Any],
        proposal: MergeProposal,
        enqueue_post_publish: bool,
    ) -> StageDResult:
        matched = await self._session.get(Module, proposal.matched_module_id)
        if matched is None or matched.lifecycle_status == "retired":
            raise ValueError(f"matched module {proposal.matched_module_id} is missing or retired")

        source_ids: set[UUID] = set(self._pipeline.extract_source_document_ids(candidate_dict))
        for sid in matched.source_document_ids or []:
            source_ids.add(sid)
        source_document_ids = sorted(source_ids)

        tenant_id = await self._resolve_ingest_tenant_id(source_document_ids)
        if matched.tenant_id != tenant_id:
            raise ValueError(
                f"matched module {matched.id} tenant_id={matched.tenant_id} "
                f"does not match ingest tenant_id={tenant_id}; refusing merge"
            )
        proposed_title = candidate_dict.get("proposed_title", "Untitled Module")
        secondary_family = await self._drafter_repo.get_or_create_module_family(
            proposed_title=proposed_title,
            tenant_id=tenant_id,
        )
        primary_family = await self._drafter_repo.get_or_create_module_family(
            proposed_title=proposed_title,
            tenant_id=tenant_id,
        )

        quality_flags: dict[str, Any] | None = (
            dict(candidate.quality_flags_jsonb) if candidate.quality_flags_jsonb else None
        )
        for family_id in (secondary_family.id, primary_family.id):
            if await self._module_repo.family_has_draft_other_than(family_id):
                qf = dict(quality_flags or {})
                flags = list(qf.get("flags") or [])
                if "family_has_existing_draft" not in flags:
                    flags.append("family_has_existing_draft")
                qf["flags"] = flags
                quality_flags = qf
                break

        created_by_user_id = await self._resolve_created_by_from_sources(source_document_ids)

        settings = get_settings()

        # Secondary (v1 in its family) = LLM-merged cards; primary (v1 in its
        # family) = new_cards. Each path has its own family, distinct from the
        # matched tip. Media is preserved from the new_cards onto merged_cards
        # (same matcher used by preserve_rich_card_bodies) then TipTap nodes
        # are embedded at persist time. The merger LLM never sees storage paths.
        merged_cards_with_media = _preserve_card_media(proposal.merged_cards, source_cards=proposal.new_cards)
        secondary = await self._drafter_repo.create_review_pending_in_family(
            family=secondary_family,
            matched=matched,
            candidate=candidate_dict,
            cards=_embed_tiptap_for_cards(merged_cards_with_media, settings=settings),
            source_document_ids=source_document_ids,
            quality_flags=quality_flags,
            match_rationale=proposal.match_rationale,
            is_merge_secondary=True,
            created_by_user_id=created_by_user_id,
            ingestion_run_id=candidate.ingestion_run_id,
        )
        primary = await self._drafter_repo.create_review_pending_in_family(
            family=primary_family,
            matched=matched,
            candidate=candidate_dict,
            cards=_embed_tiptap_for_cards(proposal.new_cards, settings=settings),
            source_document_ids=source_document_ids,
            quality_flags=quality_flags,
            match_rationale=proposal.match_rationale,
            is_merge_secondary=False,
            created_by_user_id=created_by_user_id,
            ingestion_run_id=candidate.ingestion_run_id,
        )
        primary.merge_secondary_module_id = secondary.id
        primary.merge_source_module_id = matched.id
        secondary.merge_primary_module_id = primary.id
        secondary.merge_source_module_id = matched.id
        await self._session.flush()

        if enqueue_post_publish:
            for module_id in (primary.id, secondary.id):
                await self._enqueue_post_publish(
                    module_id,
                    source_document_ids,
                    ingestion_run_id=candidate.ingestion_run_id,
                    candidate_id=candidate.id,
                )

        logger.info(
            "Stage 2-draft dual-path merge for candidate %s: primary=%s secondary=%s "
            "matched_source=%s (source left active)",
            candidate.id,
            primary.id,
            secondary.id,
            matched.id,
        )
        return StageDResult(
            candidate_id=candidate.id,
            module_id=primary.id,
            cards_count=len(proposal.new_cards),
            questions_count=0,
            insufficient_reason=None,
            merged_from_module_id=matched.id,
            was_published_merge=True,
            secondary_module_id=secondary.id,
        )

    async def _propose_published_merge(
        self,
        *,
        candidate_id: UUID,
        candidate_dict: dict[str, Any],
        cards: list[dict[str, Any]],
        valid_block_ids: set[UUID],
    ) -> MergeProposal | None:
        """Run merge LLM; return a proposal when a match is found, else None."""
        proposed_title = candidate_dict.get("proposed_title") or ""
        logger.info(
            "Stage 2-draft published merge start candidate=%s title=%r new_cards=%d valid_block_ids=%d",
            candidate_id,
            proposed_title,
            len(cards),
            len(valid_block_ids),
        )
        tenant_id = require_selected_tenant_id()
        active_rows = await self._module_repo.list_active_modules_for_merge(tenant_id=tenant_id)
        if not active_rows:
            logger.info(
                "Stage 2-draft published merge candidate=%s: no active modules; skipping",
                candidate_id,
            )
            return None

        active_ids = [row.id for row in active_rows]
        card_rows = await self._module_repo.list_cards_for_module_ids(active_ids)
        cards_by_module_id: dict[UUID, list[dict[str, Any]]] = {}
        for row in card_rows:
            if row.module_id is None:
                continue
            cards_by_module_id.setdefault(row.module_id, []).append(card_row_to_dict(row))

        existing_payloads = [
            published_module_to_merge_dict(
                m,
                _strip_media_from_cards(cards_by_module_id.get(m.id, [])),
            )
            for m in active_rows
        ]
        merge_block_ids = set(valid_block_ids)
        for payload in existing_payloads:
            merge_block_ids |= self._pipeline.block_ids_from_cards(payload.get("cards", []))

        cardinality = await resolve_for_candidate(candidate_dict, self._session)
        card_min, card_max = cardinality.card_bounds()
        logger.info(
            "Stage 2-draft published merge candidate=%s: active_modules=%d "
            "existing_cards=%d merge_block_ids=%d card_bounds=(%d,%d) active_ids=%s",
            candidate_id,
            len(active_rows),
            len(card_rows),
            len(merge_block_ids),
            card_min,
            card_max,
            [str(mid) for mid in active_ids],
        )

        try:
            merge_result = await self._published_merger.merge(
                candidate=candidate_dict,
                new_cards=_strip_media_from_cards(cards),
                existing_modules=existing_payloads,
                valid_block_ids=merge_block_ids,
                card_min_count=card_min,
                card_max_count=card_max,
            )
        except PublishedModuleMergerError:
            logger.warning(
                "Stage 2-draft module merge failed for candidate %s; using standard create",
                candidate_id,
                exc_info=True,
            )
            return None

        if merge_result.matched_module_id is None:
            logger.info(
                "Stage 2-draft published merge candidate=%s: LLM found no match "
                "(rationale=%r); using standard create",
                candidate_id,
                merge_result.match_rationale,
            )
            return None

        logger.info(
            "Stage 2-draft published merge candidate=%s: matched_module=%s raw_merged_cards=%d rationale=%r",
            candidate_id,
            merge_result.matched_module_id,
            len(merge_result.merged_cards),
            merge_result.match_rationale,
        )

        merged_cards = self._pipeline.validate_cards(
            merge_result.merged_cards,
            candidate_id=candidate_id,
        )
        if len(merged_cards) != len(merge_result.merged_cards):
            logger.info(
                "Stage 2-draft published merge candidate=%s: validate_cards dropped %d -> %d cards",
                candidate_id,
                len(merge_result.merged_cards),
                len(merged_cards),
            )
        if len(merged_cards) < card_min:
            logger.warning(
                "Stage 2-draft merge for candidate %s dropped below card_min_count "
                "(%d < %d); falling back to standard create (matched module not retired)",
                candidate_id,
                len(merged_cards),
                card_min,
            )
            return None

        matched = await self._session.get(Module, merge_result.matched_module_id)
        if matched is None or matched.lifecycle_status == "retired":
            logger.warning(
                "Stage 2-draft merge matched module %s is missing or retired (found=%s lifecycle=%s)",
                merge_result.matched_module_id,
                matched is not None,
                getattr(matched, "lifecycle_status", None),
            )
            return None

        logger.info(
            "Stage 2-draft published merge candidate=%s: proposing merge into "
            "module=%s title=%r new_cards=%d merged_cards=%d",
            candidate_id,
            matched.id,
            primary_text(matched.title_localized),
            len(cards),
            len(merged_cards),
        )
        return MergeProposal(
            matched_module_id=matched.id,
            match_rationale=merge_result.match_rationale,
            proposed_title=primary_text(matched.title_localized),
            new_cards=cards,
            merged_cards=merged_cards,
        )

    async def _enqueue_post_publish(
        self,
        module_id: UUID,
        source_document_ids: list[UUID],
        *,
        ingestion_run_id: UUID,
        candidate_id: UUID,
    ) -> None:
        await self._pipeline.enqueue_post_publish(
            module_id,
            source_document_ids,
            ingestion_run_id=ingestion_run_id,
            candidate_id=candidate_id,
        )

    @staticmethod
    def _candidate_to_dict(c: ModuleCandidateDraft) -> dict[str, Any]:
        return {
            "id": str(c.id),
            "ingestion_run_id": str(c.ingestion_run_id),
            "proposed_title": c.proposed_title,
            "scope_summary": c.scope_summary,
            "description_localized": c.description_localized,
            "domain": c.domain,
            "source_provenance": c.source_provenance_jsonb,
            "estimated_card_count": c.estimated_card_count,
            "estimated_quiz_count": c.estimated_quiz_count,
            "proposed_module_type": c.proposed_module_type,
            "previous_practice_summary": c.previous_practice_summary,
            "current_practice_summary": c.current_practice_summary,
            "rationale_summary": c.rationale_summary,
        }


__all__ = ["MergeProposal", "StageDOrchestrator", "StageDResult"]
