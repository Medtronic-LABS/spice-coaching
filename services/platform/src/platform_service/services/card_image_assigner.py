"""Card image catalog, resolver, and TipTap embed helpers for Stage D drafting.

Assignment happens at draft time: DraftPipeline builds a short-id catalog
of usable source_image alt texts, the CardDrafter LLM selects from that
catalog per card, and resolve_card_image_ids converts those short ids into
CardMediaItem JSON. embed_images_in_card_bodies then inlines TipTap image
nodes into body_localized before persist.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from mc_contracts.modules import CardMediaAnchor, CardMediaItem

from platform_service.db.models.source_image import SourceImage
from platform_service.services.card_body_text import (
    is_prosemirror_doc,
    is_rich_text_blocks,
    is_rich_text_body,
)
from platform_service.services.image_alt_text import clip_image_alt_text, is_usable_image_alt
from platform_service.services.sync.storage_path import sync_object_name

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageCatalogEntry:
    """One row in the prompt-facing image catalog."""

    short_id: str
    source_image_id: UUID
    alt_text: str
    storage_path: str
    content_type: str
    page_number: int
    start_ms: int | None
    end_ms: int | None


def build_image_catalog(images: list[SourceImage]) -> list[ImageCatalogEntry]:
    """Return catalog entries for images that have a usable alt text.

    Short ids are ``img_1``, ``img_2``, … in the order the rows are provided
    (``source_document_id``, ``page_number``, ``image_order`` from the DB query).
    Images without usable alt text are silently skipped.
    """
    entries: list[ImageCatalogEntry] = []
    counter = 0
    for img in images:
        if not is_usable_image_alt(img.alt_text):
            continue
        counter += 1
        entries.append(
            ImageCatalogEntry(
                short_id=f"img_{counter}",
                source_image_id=img.id,
                alt_text=clip_image_alt_text(img.alt_text) or "",
                storage_path=img.storage_path,
                content_type=img.content_type,
                page_number=img.page_number,
                start_ms=img.start_ms,
                end_ms=img.end_ms,
            )
        )
    return entries


def render_catalog_for_prompt(entries: list[ImageCatalogEntry]) -> str:
    """Render the ``## AVAILABLE IMAGES ##`` section for the drafter human message."""
    if not entries:
        return ""
    lines = ["\n## AVAILABLE IMAGES ##"]
    for entry in entries:
        lines.append(f"\n[image_id={entry.short_id}]\n{entry.alt_text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def resolve_card_image_ids(
    card: dict[str, Any],
    *,
    catalog_by_short_id: dict[str, ImageCatalogEntry],
    max_per_card: int,
) -> list[dict[str, Any]]:
    """Convert ``source_image_ids`` short ids on a draft card into CardMediaItem dicts.

    Returns the media list (may be empty). Unknown or duplicate ids are silently
    dropped. The result is capped at ``max_per_card``.
    """
    raw_ids = card.get("source_image_ids")
    if not raw_ids:
        return []

    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]

    block_ids = [str(b) for b in (card.get("source_block_ids") or [])]

    seen_image_ids: set[UUID] = set()
    media_items: list[dict[str, Any]] = []
    for raw_id in raw_ids:
        if len(media_items) >= max_per_card:
            break
        entry = catalog_by_short_id.get(str(raw_id).strip())
        if entry is None:
            logger.debug("card image resolve: unknown short_id %r — dropping", raw_id)
            continue
        if entry.source_image_id in seen_image_ids:
            continue
        seen_image_ids.add(entry.source_image_id)
        item = CardMediaItem(
            source_image_id=str(entry.source_image_id),
            storage_path=entry.storage_path,
            content_type=entry.content_type,
            alt=entry.alt_text or None,
            caption=entry.alt_text or None,
            anchor=CardMediaAnchor(
                field="body",
                strategy="llm_draft",
                source_page_number=entry.page_number,
                nearby_block_ids=block_ids,
                start_ms=entry.start_ms,
                end_ms=entry.end_ms,
            ),
        )
        media_items.append(item.model_dump(mode="json"))
        logger.debug(
            "card image resolve: short_id=%s image_id=%s page=%d",
            entry.short_id,
            entry.source_image_id,
            entry.page_number,
        )
    return media_items


# ---------------------------------------------------------------------------
# TipTap embed helpers
# ---------------------------------------------------------------------------


def _tiptap_image_node(*, object_name: str, alt: str | None = None) -> dict[str, Any]:
    """Build a TipTap/ProseMirror image atom with bucket-less object key."""
    attrs: dict[str, Any] = {"object_name": object_name}
    if alt and alt.strip():
        attrs["alt"] = alt.strip()
    return {"type": "image", "attrs": attrs}


def _plain_string_to_blocks(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    return [{"type": "paragraph", "content": [{"type": "text", "text": stripped}]}]


def _collect_image_object_names(value: Any) -> set[str]:
    """Harvest ``attrs.object_name`` from any nested TipTap image nodes."""
    found: set[str] = set()
    if isinstance(value, list):
        for item in value:
            found.update(_collect_image_object_names(item))
        return found
    if not isinstance(value, dict):
        return found
    if value.get("type") == "image":
        attrs = value.get("attrs")
        if isinstance(attrs, dict):
            object_name = attrs.get("object_name")
            if isinstance(object_name, str) and object_name.strip():
                found.add(object_name.strip())
    content = value.get("content")
    if isinstance(content, list):
        found.update(_collect_image_object_names(content))
    return found


def _append_image_nodes_to_locale_body(
    locale_body: Any,
    image_nodes: list[dict[str, Any]],
) -> Any:
    """Append image nodes onto one locale's body value (string or rich-text)."""
    if not image_nodes:
        return locale_body

    if locale_body is None:
        return list(image_nodes)

    if isinstance(locale_body, str):
        return [*_plain_string_to_blocks(locale_body), *image_nodes]

    if is_prosemirror_doc(locale_body):
        content = locale_body.get("content")
        existing = list(content) if isinstance(content, list) else []
        return {**locale_body, "content": [*existing, *image_nodes]}

    if is_rich_text_blocks(locale_body):
        return [*locale_body, *image_nodes]

    if is_rich_text_body(locale_body) and isinstance(locale_body, dict):
        return [locale_body, *image_nodes]

    logger.warning("card body locale value is not string/rich-text; leaving unchanged when embedding images")
    return locale_body


def embed_images_in_body_localized(
    body_localized: dict[str, Any] | None,
    *,
    media_items: list[dict[str, Any]],
    primary_locale: str,
    bucket_name: str,
) -> dict[str, Any]:
    """Return updated ``body_localized`` with TipTap image nodes for each media item.

    Plain-string locale bodies are promoted to a block list (paragraph + images).
    Image ``attrs.object_name`` is the object key only (no bucket prefix).
    Existing ``image`` nodes with the same ``object_name`` are not duplicated.
    """
    candidate_nodes: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in media_items:
        storage_path = item.get("storage_path", "")
        object_name = sync_object_name(storage_path, bucket_name=bucket_name)
        if not object_name or object_name in seen_names:
            continue
        candidate_nodes.append(_tiptap_image_node(object_name=object_name, alt=item.get("alt")))
        seen_names.add(object_name)

    if not candidate_nodes:
        return dict(body_localized) if isinstance(body_localized, dict) else {}

    if not isinstance(body_localized, dict) or not body_localized:
        return {primary_locale: list(candidate_nodes)}

    updated: dict[str, Any] = {}
    for locale, locale_body in body_localized.items():
        existing_names = _collect_image_object_names(locale_body)
        nodes_for_locale = [
            node for node in candidate_nodes if node["attrs"]["object_name"] not in existing_names
        ]
        updated[locale] = _append_image_nodes_to_locale_body(locale_body, nodes_for_locale)
    return updated


__all__ = [
    "ImageCatalogEntry",
    "build_image_catalog",
    "render_catalog_for_prompt",
    "resolve_card_image_ids",
    "embed_images_in_body_localized",
]
