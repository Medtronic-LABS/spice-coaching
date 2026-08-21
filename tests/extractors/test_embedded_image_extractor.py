"""Unit tests for native embedded image extraction + filters."""

from __future__ import annotations

from pathlib import Path

import pymupdf  # type: ignore[import-untyped]
from platform_service.workers.extractors.embedded_image_extractor import (
    ImageFilterConfig,
    extract_embedded_images,
    filter_embedded_image,
    sniff_image_content_type,
)

from tests.extractors.fixture_builders import (
    _pattern_png_bytes,
    build_docx_with_embedded_png,
    build_pdf_with_embedded_png,
    build_pptx_with_embedded_png,
)


class TestImageFilters:
    def test_rejects_unsupported_content_type(self) -> None:
        decision = filter_embedded_image(
            size_bytes=10_000,
            width_px=200,
            height_px=200,
            content_type="image/svg+xml",
            config=ImageFilterConfig(),
        )
        assert decision.keep is False
        assert decision.reason == "unsupported_content_type"

    def test_rejects_tiny_bytes(self) -> None:
        decision = filter_embedded_image(
            size_bytes=100,
            width_px=200,
            height_px=200,
            content_type="image/png",
            config=ImageFilterConfig(),
        )
        assert decision.keep is False
        assert decision.reason == "below_min_bytes"

    def test_rejects_below_min_edge(self) -> None:
        decision = filter_embedded_image(
            size_bytes=10_000,
            width_px=20,
            height_px=20,
            content_type="image/png",
            config=ImageFilterConfig(),
        )
        assert decision.keep is False
        assert decision.reason == "below_min_edge"

    def test_rejects_extreme_aspect(self) -> None:
        decision = filter_embedded_image(
            size_bytes=10_000,
            width_px=800,
            height_px=40,
            content_type="image/png",
            config=ImageFilterConfig(),
        )
        assert decision.keep is False
        assert decision.reason == "extreme_aspect_ratio"

    def test_keeps_valid_raster(self) -> None:
        decision = filter_embedded_image(
            size_bytes=10_000,
            width_px=160,
            height_px=160,
            content_type="image/png",
            config=ImageFilterConfig(),
        )
        assert decision.keep is True


class TestEmbeddedExtraction:
    def test_sniff_png(self) -> None:
        data = _pattern_png_bytes()
        assert sniff_image_content_type(data) == "image/png"
        assert len(data) >= 2048

    def test_pdf_extracts_pngs(self, tmp_path: Path) -> None:
        pdf = build_pdf_with_embedded_png(tmp_path / "fig.pdf", page_count=2)
        images = extract_embedded_images(pdf, "pdf")
        assert len(images) >= 1
        assert all(img.content_type == "image/png" for img in images)
        assert {img.page_number for img in images} <= {1, 2}
        # Deduped: same PNG blob on each page → one kept
        assert len({img.content_sha256 for img in images}) == len(images)

    def test_pdf_dedupes_identical_embeds(self, tmp_path: Path) -> None:
        pdf = build_pdf_with_embedded_png(tmp_path / "dup.pdf", page_count=2)
        images = extract_embedded_images(pdf, "pdf")
        assert len(images) == 1

    def test_pptx_extracts_picture(self, tmp_path: Path) -> None:
        pptx = build_pptx_with_embedded_png(tmp_path / "fig.pptx")
        images = extract_embedded_images(pptx, "pptx")
        assert len(images) >= 1
        assert images[0].page_number == 1
        assert images[0].content_type == "image/png"
        assert images[0].nearby_text and "Hypertension" in images[0].nearby_text

    def test_docx_extracts_picture(self, tmp_path: Path) -> None:
        docx = build_docx_with_embedded_png(tmp_path / "fig.docx")
        images = extract_embedded_images(docx, "docx")
        assert len(images) >= 1
        assert images[0].page_number == 1
        assert images[0].content_type == "image/png"
        assert images[0].nearby_text

    def test_tiny_pdf_image_filtered_out(self, tmp_path: Path) -> None:
        doc = pymupdf.open()
        page = doc.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
        pix.clear_with(200)
        page.insert_image(pymupdf.Rect(50, 50, 70, 70), pixmap=pix)
        out = tmp_path / "tiny.pdf"
        doc.save(str(out))
        doc.close()
        images = extract_embedded_images(out, "pdf")
        assert images == []
