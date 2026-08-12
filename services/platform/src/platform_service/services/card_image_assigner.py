"""Post-draft hybrid assignment of ``source_image`` rows onto module cards.

Proximity shortlists figures on pages cited by the card's ``source_block_ids``,
plus video frames whose ``start_ms`` overlaps cited AV page windows, then
embeddings re-rank caption/nearby-text against card title+body. Best-effort:
failures never fail the ingest run.
"""

from __future__ import annotations

import logging
import math
from typing import Any
from uuid import UUID

from mc_contracts.modules import CardMediaAnchor, CardMediaItem
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import Settings, get_settings
from platform_service.db.models.content_block import ContentBlock
from platform_service.db.models.module_card import ModuleCard
from platform_service.db.models.source_image import SourceImage
from platform_service.db.models.source_page import SourcePage
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.localized import deployment_locales, primary_text
from platform_service.services.card_body_text import card_body_plain_text

logger = logging.getLogger(__name__)

# block_id -> (page_number, block_order, start_ms, end_ms)
BlockPageInfo = tuple[int, int, int | None, int | None]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _card_plain_text(card: ModuleCard, *, settings: Settings) -> str:
    parts: list[str] = []
    title = primary_text(card.title_localized, settings=settings)
    if title:
        parts.append(title)
    body_localized = card.body_localized
    if isinstance(body_localized, dict):
        primary = deployment_locales(settings)
        locale_body = body_localized.get(primary)
        if locale_body is None and body_localized:
            locale_body = next(iter(body_localized.values()), None)
        plain = card_body_plain_text(locale_body)
        if plain:
            parts.append(plain)
    elif body_localized is not None:
        plain = card_body_plain_text(body_localized)
        if plain:
            parts.append(plain)
    return "\n".join(parts).strip()


def _image_match_text(image: SourceImage) -> str:
    parts: list[str] = []
    if image.alt_text:
        parts.append(image.alt_text.strip())
    if image.nearby_text:
        parts.append(image.nearby_text.strip())
    return "\n".join(p for p in parts if p).strip()


def _ranges_overlap(
    a_start: int | None,
    a_end: int | None,
    b_start: int | None,
    b_end: int | None,
) -> bool:
    """True when two half-open or point ranges overlap."""
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return False
    return a_start <= b_end and b_start <= a_end


def _image_overlaps_ranges(
    image: SourceImage,
    ranges: list[tuple[int, int]],
) -> bool:
    if image.start_ms is None:
        return False
    img_end = image.end_ms if image.end_ms is not None else image.start_ms
    for start, end in ranges:
        if _ranges_overlap(image.start_ms, img_end, start, end):
            return True
    return False


class CardImageAssigner:
    """Assign extracted source images to module cards after Stage D persist."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        ai_client: AIRuntimeClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._ai = ai_client
        self._repo = SourceRepository(session)

    def _get_ai(self) -> AIRuntimeClient:
        if self._ai is None:
            self._ai = AIRuntimeClient()
        return self._ai

    async def assign_for_module(
        self,
        *,
        module_id: UUID,
        source_document_ids: list[UUID],
    ) -> int:
        """Write ``media_jsonb`` on cards. Returns number of cards updated."""
        if not self._settings.ingest_card_image_assignment_enabled:
            return 0
        if not source_document_ids:
            return 0

        try:
            images = await self._repo.list_images_for_documents(source_document_ids)
            if not images:
                return 0

            cards_result = await self._session.execute(
                select(ModuleCard).where(ModuleCard.module_id == module_id).order_by(ModuleCard.card_order)
            )
            cards = list(cards_result.scalars().all())
            if not cards:
                return 0

            block_ids = {bid for card in cards if card.source_block_ids for bid in card.source_block_ids}
            block_page: dict[UUID, BlockPageInfo] = {}
            if block_ids:
                rows = await self._session.execute(
                    select(
                        ContentBlock.id,
                        ContentBlock.block_order,
                        SourcePage.page_number,
                        SourcePage.start_ms,
                        SourcePage.end_ms,
                    )
                    .join(SourcePage, ContentBlock.source_page_id == SourcePage.id)
                    .where(ContentBlock.id.in_(list(block_ids)))
                )
                for block_id, block_order, page_number, start_ms, end_ms in rows.all():
                    block_page[block_id] = (
                        int(page_number),
                        int(block_order),
                        int(start_ms) if start_ms is not None else None,
                        int(end_ms) if end_ms is not None else None,
                    )

            images_by_page: dict[int, list[SourceImage]] = {}
            for image in images:
                images_by_page.setdefault(image.page_number, []).append(image)

            used_image_ids: set[UUID] = set()
            updated = 0
            for card in cards:
                media = await self._assign_card(
                    card=card,
                    block_page=block_page,
                    images_by_page=images_by_page,
                    all_images=images,
                    used_image_ids=used_image_ids,
                )
                if media:
                    card.media_jsonb = media
                    updated += 1

            if updated:
                await self._session.flush()
                logger.info(
                    "card image assignment module_id=%s cards_with_media=%d",
                    module_id,
                    updated,
                )
            return updated
        except Exception:
            logger.exception(
                "card image assignment failed module_id=%s (continuing without media)",
                module_id,
            )
            return 0

    async def _assign_card(
        self,
        *,
        card: ModuleCard,
        block_page: dict[UUID, BlockPageInfo],
        images_by_page: dict[int, list[SourceImage]],
        all_images: list[SourceImage],
        used_image_ids: set[UUID],
    ) -> list[dict[str, Any]]:
        cited = list(card.source_block_ids or [])
        if not cited:
            return []

        page_numbers: set[int] = set()
        block_orders: list[int] = []
        time_ranges: list[tuple[int, int]] = []
        for bid in cited:
            info = block_page.get(bid)
            if info is None:
                continue
            page_number, block_order, start_ms, end_ms = info
            page_numbers.add(page_number)
            block_orders.append(block_order)
            if start_ms is not None and end_ms is not None:
                time_ranges.append((start_ms, end_ms))

        candidates: list[SourceImage] = []
        seen: set[UUID] = set()
        for pn in sorted(page_numbers):
            for image in images_by_page.get(pn, []):
                if image.id in used_image_ids or image.id in seen:
                    continue
                candidates.append(image)
                seen.add(image.id)

        # Video frames on other page numbers that overlap cited AV windows.
        if time_ranges:
            for image in all_images:
                if image.id in used_image_ids or image.id in seen:
                    continue
                if _image_overlaps_ranges(image, time_ranges):
                    candidates.append(image)
                    seen.add(image.id)

        # DOCX / sparse page overlap: fall back to all unused doc images.
        if not candidates and len(page_numbers) <= 1:
            for image in all_images:
                if image.id not in used_image_ids:
                    candidates.append(image)

        if not candidates:
            return []

        # Prefer images whose order is near cited block orders (stable sort).
        mid_order = (
            sum(block_orders) / len(block_orders) if block_orders else float(candidates[0].image_order)
        )
        candidates.sort(key=lambda img: (abs(img.image_order - mid_order), img.page_number, img.image_order))

        card_text = _card_plain_text(card, settings=self._settings)
        ranked = await self._rerank(card_text=card_text, candidates=candidates)

        max_per = max(1, int(self._settings.ingest_card_image_max_per_card))
        min_cosine = float(self._settings.ingest_card_image_min_cosine)
        selected: list[tuple[SourceImage, float, str]] = []
        for image, score, strategy in ranked:
            if len(selected) >= max_per:
                break
            if image.id in used_image_ids:
                continue
            # When embeddings available, enforce threshold; proximity-only keeps top-N.
            if strategy == "hybrid" and score < min_cosine:
                continue
            selected.append((image, score, strategy))
            used_image_ids.add(image.id)

        media_items: list[dict[str, Any]] = []
        for image, _score, strategy in selected:
            item = CardMediaItem(
                source_image_id=str(image.id),
                storage_path=image.storage_path,
                content_type=image.content_type,
                alt=image.alt_text,
                caption=image.nearby_text,
                anchor=CardMediaAnchor(
                    field="body",
                    strategy="hybrid" if strategy == "hybrid" else "source_proximity",
                    source_page_number=image.page_number,
                    nearby_block_ids=[str(b) for b in cited],
                    start_ms=image.start_ms,
                    end_ms=image.end_ms,
                ),
            )
            media_items.append(item.model_dump(mode="json"))
        return media_items

    async def _rerank(
        self,
        *,
        card_text: str,
        candidates: list[SourceImage],
    ) -> list[tuple[SourceImage, float, str]]:
        """Return candidates ordered best-first with score + strategy label."""
        if not card_text.strip():
            return [(img, 0.0, "source_proximity") for img in candidates]

        image_texts = [_image_match_text(img) for img in candidates]
        # If no image has nearby/alt text, stay on proximity order.
        if not any(t for t in image_texts):
            return [(img, 0.0, "source_proximity") for img in candidates]

        texts = [card_text, *[t or " " for t in image_texts]]
        try:
            vectors = await self._get_ai().embed(texts)
        except Exception:
            logger.warning(
                "card image embed re-rank failed; using proximity order only",
                exc_info=True,
            )
            return [(img, 0.0, "source_proximity") for img in candidates]

        if len(vectors) != len(texts):
            return [(img, 0.0, "source_proximity") for img in candidates]

        card_vec = vectors[0]
        scored: list[tuple[SourceImage, float, str]] = []
        for image, vec in zip(candidates, vectors[1:], strict=True):
            scored.append((image, _cosine(card_vec, vec), "hybrid"))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored


__all__ = ["CardImageAssigner"]
