"""Unit tests for post-draft card image assignment."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from platform_service.config import Settings
from platform_service.db.models.module_card import ModuleCard
from platform_service.db.models.source_image import SourceImage
from platform_service.services.card_image_assigner import CardImageAssigner, _cosine
from platform_service.services.card_normalisation import card_dict_to_row_fields, card_row_to_dict


def test_cosine_identical() -> None:
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal() -> None:
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


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
                "strategy": "hybrid",
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


@pytest.mark.asyncio
async def test_assigner_flag_off_is_noop() -> None:
    session = AsyncMock()
    settings = Settings(ingest_card_image_assignment_enabled=False)
    assigner = CardImageAssigner(session, settings=settings)
    updated = await assigner.assign_for_module(module_id=uuid4(), source_document_ids=[uuid4()])
    assert updated == 0


@pytest.mark.asyncio
async def test_assign_card_hybrid_orders_by_cosine() -> None:
    settings = Settings(
        ingest_card_image_assignment_enabled=True,
        ingest_card_image_max_per_card=1,
        ingest_card_image_min_cosine=0.2,
        deployment_primary_locale="bn",
    )
    block_id = uuid4()
    img_near = SourceImage(
        id=uuid4(),
        source_document_id=uuid4(),
        source_page_id=None,
        page_number=1,
        image_order=0,
        storage_path="b/ingest/figures/a.png",
        content_type="image/png",
        content_sha256="aaa",
        width_px=160,
        height_px=160,
        size_bytes=5000,
        alt_text=None,
        nearby_text="blood pressure hypertension chart",
        bbox_jsonb=None,
    )
    img_far = SourceImage(
        id=uuid4(),
        source_document_id=img_near.source_document_id,
        source_page_id=None,
        page_number=1,
        image_order=1,
        storage_path="b/ingest/figures/b.png",
        content_type="image/png",
        content_sha256="bbb",
        width_px=160,
        height_px=160,
        size_bytes=5000,
        alt_text=None,
        nearby_text="unrelated logo branding",
        bbox_jsonb=None,
    )
    card = ModuleCard(
        id=uuid4(),
        module_id=uuid4(),
        card_order=1,
        card_family_id=uuid4(),
        card_version=1,
        title_localized={"bn": "Hypertension screening"},
        body_localized={"bn": "Measure blood pressure and chart results."},
        source_block_ids=[block_id],
    )

    ai = AsyncMock()
    ai.embed = AsyncMock(
        return_value=[
            [1.0, 0.0, 0.0],
            [0.99, 0.1, 0.0],
            [0.0, 1.0, 0.0],
        ]
    )
    assigner = CardImageAssigner(AsyncMock(), settings=settings, ai_client=ai)
    media = await assigner._assign_card(  # noqa: SLF001
        card=card,
        block_page={block_id: (1, 0, None, None)},
        images_by_page={1: [img_near, img_far]},
        all_images=[img_near, img_far],
        used_image_ids=set(),
    )
    assert len(media) == 1
    assert media[0]["source_image_id"] == str(img_near.id)
    assert media[0]["anchor"]["strategy"] == "hybrid"


@pytest.mark.asyncio
async def test_assign_card_time_overlap_includes_video_frame() -> None:
    settings = Settings(
        ingest_card_image_assignment_enabled=True,
        ingest_card_image_max_per_card=1,
        ingest_card_image_min_cosine=0.2,
        deployment_primary_locale="bn",
    )
    block_id = uuid4()
    doc_id = uuid4()
    # Frame lives on page 2 but overlaps cited page-1 time window.
    img = SourceImage(
        id=uuid4(),
        source_document_id=doc_id,
        source_page_id=None,
        page_number=2,
        image_order=0,
        storage_path="b/ingest/figures/frame.png",
        content_type="image/png",
        content_sha256="frame",
        width_px=160,
        height_px=160,
        size_bytes=5000,
        alt_text="slide",
        nearby_text="blood pressure chart on screen",
        bbox_jsonb={"kind": "video_frame"},
        start_ms=45_000,
        end_ms=45_000,
    )
    card = ModuleCard(
        id=uuid4(),
        module_id=uuid4(),
        card_order=1,
        card_family_id=uuid4(),
        card_version=1,
        title_localized={"bn": "Hypertension screening"},
        body_localized={"bn": "Measure blood pressure and chart results."},
        source_block_ids=[block_id],
    )
    ai = AsyncMock()
    ai.embed = AsyncMock(return_value=[[1.0, 0.0], [0.99, 0.1]])
    assigner = CardImageAssigner(AsyncMock(), settings=settings, ai_client=ai)
    media = await assigner._assign_card(  # noqa: SLF001
        card=card,
        block_page={block_id: (1, 0, 0, 120_000)},
        images_by_page={1: []},
        all_images=[img],
        used_image_ids=set(),
    )
    assert len(media) == 1
    assert media[0]["source_image_id"] == str(img.id)
    assert media[0]["anchor"]["start_ms"] == 45_000
    assert media[0]["anchor"]["end_ms"] == 45_000


@pytest.mark.asyncio
async def test_rerank_falls_back_to_proximity_on_embed_failure() -> None:
    settings = Settings(ingest_card_image_assignment_enabled=True)
    img = SourceImage(
        id=uuid4(),
        source_document_id=uuid4(),
        source_page_id=None,
        page_number=1,
        image_order=0,
        storage_path="b/ingest/figures/a.png",
        content_type="image/png",
        content_sha256="aaa",
        width_px=160,
        height_px=160,
        size_bytes=5000,
        alt_text="alt",
        nearby_text="nearby",
        bbox_jsonb=None,
    )
    ai = AsyncMock()
    ai.embed = AsyncMock(side_effect=RuntimeError("boom"))
    assigner = CardImageAssigner(AsyncMock(), settings=settings, ai_client=ai)
    ranked = await assigner._rerank(card_text="card", candidates=[img])  # noqa: SLF001
    assert ranked == [(img, 0.0, "source_proximity")]
