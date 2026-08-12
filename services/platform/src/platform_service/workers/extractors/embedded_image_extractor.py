"""Native embedded-image extraction for PDF / PPTX / DOCX (Stage A).

Extracts picture bytes already embedded in the source file — no page raster
or LibreOffice path. Decorative/tiny/unsupported formats are filtered out.
"""

from __future__ import annotations

import hashlib
import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf  # type: ignore[import-untyped]
from docx import Document as DocxDocument  # type: ignore[import-untyped]
from docx.oxml.ns import qn  # type: ignore[import-untyped]
from pptx import Presentation  # type: ignore[import-untyped]
from pptx.enum.shapes import MSO_SHAPE_TYPE  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
    }
)

_EXT_TO_CONTENT_TYPE: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


@dataclass(frozen=True)
class ExtractedEmbeddedImage:
    """One native embedded image candidate before object-store persistence."""

    page_number: int
    image_order: int
    data: bytes
    content_type: str
    content_sha256: str
    width_px: int | None
    height_px: int | None
    size_bytes: int
    alt_text: str | None = None
    nearby_text: str | None = None
    bbox_jsonb: dict[str, Any] | None = None


@dataclass(frozen=True)
class ImageFilterConfig:
    min_edge_px: int = 64
    min_bytes: int = 2048
    max_aspect_ratio: float = 12.0
    min_strip_edge_px: int = 32


@dataclass(frozen=True)
class FilterDecision:
    keep: bool
    reason: str


def content_type_for_ext(ext: str | None) -> str | None:
    if not ext:
        return None
    return _EXT_TO_CONTENT_TYPE.get(ext.lstrip(".").lower())


def extension_for_content_type(content_type: str) -> str | None:
    return _CONTENT_TYPE_TO_EXT.get(content_type.split(";", maxsplit=1)[0].strip().lower())


def sniff_image_content_type(data: bytes) -> str | None:
    """Detect PNG / JPEG / WebP from magic bytes."""
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def raster_dimensions(data: bytes, content_type: str | None = None) -> tuple[int | None, int | None]:
    """Return (width, height) for PNG/JPEG when headers are parseable."""
    ctype = content_type or sniff_image_content_type(data)
    if ctype == "image/png" and len(data) >= 24:
        # IHDR width/height are big-endian u32 at offset 16.
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    if ctype == "image/jpeg":
        return _jpeg_dimensions(data)
    if ctype == "image/webp":
        return _webp_dimensions(data)
    return None, None


def _jpeg_dimensions(data: bytes) -> tuple[int | None, int | None]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None, None
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return int(width), int(height)
        if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7):
            i += 2
            continue
        if i + 3 >= len(data):
            break
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        i += 2 + length
    return None, None


def _webp_dimensions(data: bytes) -> tuple[int | None, int | None]:
    if len(data) < 30:
        return None, None
    # VP8X: canvas width/height are 24-bit little-endian (minus one) at 24..29
    if data[12:16] == b"VP8X" and len(data) >= 30:
        w = 1 + int.from_bytes(data[24:27], "little")
        h = 1 + int.from_bytes(data[27:30], "little")
        return w, h
    # VP8 (lossy): frame tag at 23; width/height in next 4 bytes (14-bit each)
    if data[12:16] == b"VP8 " and len(data) >= 30:
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return int(width), int(height)
    # VP8L (lossless): 14-bit width-1 / height-1 packed after signature
    if data[12:16] == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = struct.unpack("<I", data[21:25])[0]
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return int(width), int(height)
    return None, None


def filter_embedded_image(
    *,
    size_bytes: int,
    width_px: int | None,
    height_px: int | None,
    content_type: str | None,
    config: ImageFilterConfig,
) -> FilterDecision:
    if content_type not in ALLOWED_CONTENT_TYPES:
        return FilterDecision(False, "unsupported_content_type")
    if size_bytes < config.min_bytes:
        return FilterDecision(False, "below_min_bytes")
    if width_px is not None and height_px is not None:
        if width_px < config.min_edge_px and height_px < config.min_edge_px:
            return FilterDecision(False, "below_min_edge")
        if min(width_px, height_px) < config.min_strip_edge_px:
            return FilterDecision(False, "thin_strip")
        longer = max(width_px, height_px)
        shorter = max(min(width_px, height_px), 1)
        if longer / shorter > config.max_aspect_ratio:
            return FilterDecision(False, "extreme_aspect_ratio")
    return FilterDecision(True, "ok")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clip_nearby(text: str, *, max_chars: int = 500) -> str | None:
    cleaned = " ".join(text.split())
    if not cleaned:
        return None
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def extract_embedded_images(
    source_path: str | Path,
    source_type: str,
    *,
    filter_config: ImageFilterConfig | None = None,
) -> list[ExtractedEmbeddedImage]:
    """Extract filtered, deduped embedded images for a supported document type."""
    cfg = filter_config or ImageFilterConfig()
    path = Path(source_path)
    if source_type == "pdf":
        raw = _extract_pdf(path)
    elif source_type == "pptx":
        raw = _extract_pptx(path)
    elif source_type == "docx":
        raw = _extract_docx(path)
    else:
        return []

    kept: list[ExtractedEmbeddedImage] = []
    seen_hashes: set[str] = set()
    skipped: dict[str, int] = {}
    for candidate in raw:
        decision = filter_embedded_image(
            size_bytes=candidate.size_bytes,
            width_px=candidate.width_px,
            height_px=candidate.height_px,
            content_type=candidate.content_type,
            config=cfg,
        )
        if not decision.keep:
            skipped[decision.reason] = skipped.get(decision.reason, 0) + 1
            continue
        if candidate.content_sha256 in seen_hashes:
            skipped["duplicate_sha256"] = skipped.get("duplicate_sha256", 0) + 1
            continue
        seen_hashes.add(candidate.content_sha256)
        kept.append(candidate)

    if skipped:
        logger.info(
            "embedded_image_filter source_type=%s kept=%d skipped=%s",
            source_type,
            len(kept),
            skipped,
        )
    return kept


def _build_image(
    *,
    page_number: int,
    image_order: int,
    data: bytes,
    content_type: str | None = None,
    width_px: int | None = None,
    height_px: int | None = None,
    alt_text: str | None = None,
    nearby_text: str | None = None,
    bbox_jsonb: dict[str, Any] | None = None,
) -> ExtractedEmbeddedImage | None:
    ctype = content_type or sniff_image_content_type(data)
    if ctype is None:
        return None
    w, h = width_px, height_px
    if w is None or h is None:
        sniffed_w, sniffed_h = raster_dimensions(data, ctype)
        w = w if w is not None else sniffed_w
        h = h if h is not None else sniffed_h
    return ExtractedEmbeddedImage(
        page_number=page_number,
        image_order=image_order,
        data=data,
        content_type=ctype,
        content_sha256=_sha256_hex(data),
        width_px=w,
        height_px=h,
        size_bytes=len(data),
        alt_text=alt_text,
        nearby_text=_clip_nearby(nearby_text) if nearby_text else None,
        bbox_jsonb=bbox_jsonb,
    )


def _extract_pdf(path: Path) -> list[ExtractedEmbeddedImage]:
    out: list[ExtractedEmbeddedImage] = []
    order = 0
    with pymupdf.open(path) as doc:
        for page_index in range(len(doc)):
            page = doc[page_index]
            page_number = page_index + 1
            page_text = page.get_text("text") or ""
            image_list = page.get_images(full=True)
            # Map xref → list of rects when available.
            rects_by_xref: dict[int, list[Any]] = {}
            try:
                for img_info in page.get_image_info(xrefs=True):
                    xref = int(img_info.get("xref") or 0)
                    if xref <= 0:
                        continue
                    bbox = img_info.get("bbox")
                    if bbox is not None:
                        rects_by_xref.setdefault(xref, []).append(bbox)
            except Exception:
                logger.debug("pdf get_image_info unavailable page=%s", page_number, exc_info=True)

            for img in image_list:
                xref = int(img[0])
                try:
                    extracted = doc.extract_image(xref)
                except Exception:
                    logger.debug("pdf extract_image failed xref=%s", xref, exc_info=True)
                    continue
                data = extracted.get("image") or b""
                if not data:
                    continue
                ext = str(extracted.get("ext") or "").lower()
                ctype = content_type_for_ext(ext) or sniff_image_content_type(data)
                width = extracted.get("width")
                height = extracted.get("height")
                bbox = None
                rects = rects_by_xref.get(xref) or []
                if rects:
                    r = rects[0]
                    bbox = {
                        "x0": float(r[0]),
                        "y0": float(r[1]),
                        "x1": float(r[2]),
                        "y1": float(r[3]),
                    }
                nearby = page_text
                if bbox is not None:
                    try:
                        clip = pymupdf.Rect(bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
                        # Expand clip slightly for caption-like text under the figure.
                        clip = clip + (-20, -40, 20, 80)
                        nearby = page.get_text("text", clip=clip) or page_text
                    except Exception:
                        nearby = page_text
                built = _build_image(
                    page_number=page_number,
                    image_order=order,
                    data=data,
                    content_type=ctype,
                    width_px=int(width) if width else None,
                    height_px=int(height) if height else None,
                    nearby_text=nearby,
                    bbox_jsonb=bbox,
                )
                if built is not None:
                    out.append(built)
                    order += 1
    return out


def _pptx_slide_text(slide) -> str:
    parts: list[str] = []
    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        for paragraph in shape.text_frame.paragraphs:
            text = "".join(run.text or "" for run in paragraph.runs).strip()
            if not text:
                text = (paragraph.text or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _extract_pptx(path: Path) -> list[ExtractedEmbeddedImage]:
    out: list[ExtractedEmbeddedImage] = []
    order = 0
    prs = Presentation(str(path))
    for slide_index, slide in enumerate(prs.slides, start=1):
        nearby = _pptx_slide_text(slide)
        for shape in slide.shapes:
            if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue
            try:
                image = shape.image
                data = image.blob
                ctype = sniff_image_content_type(data)
                if ctype is None and image.content_type:
                    raw_ctype = str(image.content_type).split(";", maxsplit=1)[0].strip().lower()
                    if raw_ctype in ALLOWED_CONTENT_TYPES:
                        ctype = raw_ctype
                alt = None
                try:
                    alt = (shape.name or "").strip() or None
                except Exception:
                    alt = None
                built = _build_image(
                    page_number=slide_index,
                    image_order=order,
                    data=data,
                    content_type=ctype,
                    alt_text=alt,
                    nearby_text=nearby,
                )
                if built is not None:
                    out.append(built)
                    order += 1
            except Exception:
                logger.debug("pptx picture extract failed slide=%s", slide_index, exc_info=True)
                continue
    return out


def _docx_paragraphs_text(doc: DocxDocument) -> list[str]:
    return [(p.text or "").strip() for p in doc.paragraphs]


def _extract_docx(path: Path) -> list[ExtractedEmbeddedImage]:
    """Extract inline pictures from a DOCX; whole document is page 1."""
    out: list[ExtractedEmbeddedImage] = []
    order = 0
    doc = DocxDocument(str(path))
    para_texts = _docx_paragraphs_text(doc)
    # Walk body elements to associate images with nearby paragraph text.
    body = doc.element.body
    para_idx = -1
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            para_idx += 1
            # Images may sit inside runs as drawing/blip.
            blips = child.findall(".//" + qn("a:blip"))
            if not blips:
                continue
            nearby_parts: list[str] = []
            if 0 <= para_idx < len(para_texts) and para_texts[para_idx]:
                nearby_parts.append(para_texts[para_idx])
            if para_idx > 0 and para_texts[para_idx - 1]:
                nearby_parts.insert(0, para_texts[para_idx - 1])
            if para_idx + 1 < len(para_texts) and para_texts[para_idx + 1]:
                nearby_parts.append(para_texts[para_idx + 1])
            nearby = "\n".join(nearby_parts)
            for blip in blips:
                embed = blip.get(qn("r:embed"))
                if not embed:
                    continue
                try:
                    part = doc.part.related_parts[embed]
                    data = part.blob
                except Exception:
                    logger.debug("docx blip resolve failed", exc_info=True)
                    continue
                ctype = sniff_image_content_type(data)
                if ctype is None:
                    raw_ctype = getattr(part, "content_type", None)
                    if isinstance(raw_ctype, str):
                        candidate = raw_ctype.split(";", maxsplit=1)[0].strip().lower()
                        if candidate in ALLOWED_CONTENT_TYPES:
                            ctype = candidate
                built = _build_image(
                    page_number=1,
                    image_order=order,
                    data=data,
                    content_type=ctype,
                    nearby_text=nearby,
                )
                if built is not None:
                    out.append(built)
                    order += 1
    return out


__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "ExtractedEmbeddedImage",
    "FilterDecision",
    "ImageFilterConfig",
    "content_type_for_ext",
    "extension_for_content_type",
    "extract_embedded_images",
    "filter_embedded_image",
    "raster_dimensions",
    "sniff_image_content_type",
]
