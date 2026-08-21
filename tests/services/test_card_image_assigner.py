"""Unit tests for the card image catalog, resolver, and TipTap embed helpers."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from platform_service.db.models.source_image import SourceImage
from platform_service.services.card_image_assigner import (
    ImageCatalogEntry,
    build_image_catalog,
    embed_images_in_body_localized,
    render_catalog_for_prompt,
    resolve_card_image_ids,
)
from platform_service.services.card_normalisation import card_dict_to_row_fields, card_row_to_dict


def _source_image(*, alt_text: str | None = "A chart", page_number: int = 1) -> SourceImage:
    return SourceImage(
        id=uuid4(),
        source_document_id=uuid4(),
        source_page_id=None,
        page_number=page_number,
        image_order=0,
        storage_path="bucket/ingest/figures/x.png",
        content_type="image/png",
        content_sha256="aaa",
        width_px=100,
        height_px=100,
        size_bytes=1000,
        alt_text=alt_text,
        nearby_text=None,
        bbox_jsonb=None,
    )


# ---------------------------------------------------------------------------
# Catalog builder
# ---------------------------------------------------------------------------


def test_build_image_catalog_skips_empty_alt() -> None:
    img_ok = _source_image(alt_text="Blood pressure chart")
    img_empty = _source_image(alt_text=None)
    img_placeholder = _source_image(alt_text="Picture 3")
    catalog = build_image_catalog([img_ok, img_empty, img_placeholder])
    assert len(catalog) == 1
    assert catalog[0].short_id == "img_1"
    assert catalog[0].source_image_id == img_ok.id
    assert catalog[0].alt_text == "Blood pressure chart"


def test_build_image_catalog_assigns_sequential_ids() -> None:
    images = [_source_image(alt_text=f"BP chart {i}") for i in range(3)]
    catalog = build_image_catalog(images)
    assert [e.short_id for e in catalog] == ["img_1", "img_2", "img_3"]


def test_build_image_catalog_empty_when_no_images() -> None:
    assert build_image_catalog([]) == []


# ---------------------------------------------------------------------------
# Prompt render
# ---------------------------------------------------------------------------


def test_render_catalog_for_prompt_empty_produces_empty_string() -> None:
    assert render_catalog_for_prompt([]) == ""


def test_render_catalog_for_prompt_contains_short_id_and_alt() -> None:
    img = _source_image(alt_text="BP chart")
    catalog = build_image_catalog([img])
    rendered = render_catalog_for_prompt(catalog)
    assert "img_1" in rendered
    assert "BP chart" in rendered
    assert "## AVAILABLE IMAGES ##" in rendered


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def _catalog_entry(short_id: str, *, alt: str = "A chart") -> ImageCatalogEntry:
    return ImageCatalogEntry(
        short_id=short_id,
        source_image_id=uuid4(),
        alt_text=alt,
        storage_path=f"bucket/ingest/figures/{short_id}.png",
        content_type="image/png",
        page_number=1,
        start_ms=None,
        end_ms=None,
    )


def test_resolve_valid_ids_produces_media_items() -> None:
    entry = _catalog_entry("img_1", alt="BP chart")
    catalog = {"img_1": entry}
    block_id = str(uuid4())
    card = {"source_image_ids": ["img_1"], "source_block_ids": [block_id]}
    media = resolve_card_image_ids(card, catalog_by_short_id=catalog, max_per_card=5)
    assert len(media) == 1
    assert media[0]["source_image_id"] == str(entry.source_image_id)
    assert media[0]["anchor"]["strategy"] == "llm_draft"
    assert media[0]["anchor"]["nearby_block_ids"] == [block_id]
    assert media[0]["alt"] == "BP chart"


def test_resolve_unknown_id_is_silently_dropped() -> None:
    catalog = {"img_1": _catalog_entry("img_1")}
    card = {"source_image_ids": ["img_99"], "source_block_ids": []}
    media = resolve_card_image_ids(card, catalog_by_short_id=catalog, max_per_card=5)
    assert media == []


def test_resolve_capped_at_max_per_card() -> None:
    catalog = {f"img_{i}": _catalog_entry(f"img_{i}", alt=f"Image {i}") for i in range(5)}
    card = {
        "source_image_ids": [f"img_{i}" for i in range(5)],
        "source_block_ids": [],
    }
    media = resolve_card_image_ids(card, catalog_by_short_id=catalog, max_per_card=2)
    assert len(media) == 2


def test_resolve_duplicate_ids_deduplicated() -> None:
    entry = _catalog_entry("img_1")
    catalog = {"img_1": entry}
    card = {"source_image_ids": ["img_1", "img_1"], "source_block_ids": []}
    media = resolve_card_image_ids(card, catalog_by_short_id=catalog, max_per_card=5)
    assert len(media) == 1


def test_resolve_empty_catalog_returns_empty() -> None:
    card = {"source_image_ids": ["img_1"], "source_block_ids": []}
    media = resolve_card_image_ids(card, catalog_by_short_id={}, max_per_card=5)
    assert media == []


def test_resolve_no_source_image_ids_returns_empty() -> None:
    catalog = {"img_1": _catalog_entry("img_1")}
    card = {"source_block_ids": []}
    media = resolve_card_image_ids(card, catalog_by_short_id=catalog, max_per_card=5)
    assert media == []


def test_resolve_same_id_reused_across_different_cards() -> None:
    entry = _catalog_entry("img_1")
    catalog = {"img_1": entry}
    card_a = {"source_image_ids": ["img_1"], "source_block_ids": []}
    card_b = {"source_image_ids": ["img_1"], "source_block_ids": []}
    media_a = resolve_card_image_ids(card_a, catalog_by_short_id=catalog, max_per_card=5)
    media_b = resolve_card_image_ids(card_b, catalog_by_short_id=catalog, max_per_card=5)
    assert len(media_a) == 1
    assert len(media_b) == 1
    assert media_a[0]["source_image_id"] == media_b[0]["source_image_id"]


# ---------------------------------------------------------------------------
# TipTap embed
# ---------------------------------------------------------------------------


def test_embed_promotes_plain_string_body() -> None:
    media = [
        {
            "storage_path": "bucket/ingest/figures/x.png",
            "alt": "BP chart",
        }
    ]
    updated = embed_images_in_body_localized(
        {"bn": "শোথ একটি লক্ষণ।"},
        media_items=media,
        primary_locale="bn",
        bucket_name="bucket",
    )
    assert updated == {
        "bn": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "শোথ একটি লক্ষণ।"}],
            },
            {
                "type": "image",
                "attrs": {"object_name": "ingest/figures/x.png", "alt": "BP chart"},
            },
        ]
    }


def test_embed_appends_to_block_list_and_skips_duplicates() -> None:
    object_name = "ingest/figures/x.png"
    existing = {
        "bn": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Existing"}],
            },
            {"type": "image", "attrs": {"object_name": object_name}},
        ]
    }
    media = [{"storage_path": f"bucket/{object_name}", "alt": None}]
    updated = embed_images_in_body_localized(
        existing,
        media_items=media,
        primary_locale="bn",
        bucket_name="bucket",
    )
    assert updated == existing


def test_embed_appends_into_prosemirror_doc() -> None:
    body = {
        "bn": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello"}],
                }
            ],
        }
    }
    media = [{"storage_path": "bucket/ingest/figures/fig.png", "alt": None}]
    updated = embed_images_in_body_localized(
        body,
        media_items=media,
        primary_locale="bn",
        bucket_name="bucket",
    )
    assert updated["bn"]["type"] == "doc"
    assert updated["bn"]["content"][-1] == {
        "type": "image",
        "attrs": {"object_name": "ingest/figures/fig.png"},
    }


def test_embed_empty_media_returns_original_body() -> None:
    body = {"bn": "Some text"}
    updated = embed_images_in_body_localized(
        body,
        media_items=[],
        primary_locale="bn",
        bucket_name="bucket",
    )
    assert updated == body


# ---------------------------------------------------------------------------
# Card normalisation roundtrip (media survives project_runtime_card)
# ---------------------------------------------------------------------------


def test_card_normalisation_roundtrips_media() -> None:
    media = [
        {
            "source_image_id": str(uuid4()),
            "storage_path": "bucket/ingest/figures/x/a.png",
            "content_type": "image/png",
            "alt": "chart",
            "caption": "BP chart",
            "anchor": {
                "field": "body",
                "strategy": "llm_draft",
                "source_page_number": 2,
                "nearby_block_ids": [],
            },
        }
    ]
    row_fields = card_dict_to_row_fields(
        {
            "title": {"bn": "Title"},
            "body": {"bn": "Body"},
            "media": media,
        }
    )
    assert row_fields["media_jsonb"] == media
    row = SimpleNamespace(
        id=uuid4(),
        card_family_id=uuid4(),
        card_order=1,
        title_localized={"bn": "Title"},
        body_localized={"bn": "Body"},
        previous_practice_localized=None,
        current_practice_localized=None,
        rationale_for_change_localized=None,
        next_action_localized=None,
        thresholds_jsonb=None,
        source_block_ids=None,
        figure_ref_block_id=None,
        search_metadata_jsonb=None,
        attachments_jsonb=None,
        media_jsonb=media,
        field_flags_jsonb=None,
    )
    payload = card_row_to_dict(row)
    assert payload["media"] == media
