"""Unit tests for Stage A source_image persist alt resolution."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from platform_service.config import Settings
from platform_service.services.source_image_persist_service import SourceImagePersistService
from platform_service.workers.extractors.embedded_image_extractor import ExtractedEmbeddedImage
from platform_service.workers.extractors.vision_extractor import VisionExtractionError


def _image(**overrides: object) -> ExtractedEmbeddedImage:
    data = b"\x89PNG\r\n\x1a\n" + b"x" * 3000
    fields: dict[str, object] = {
        "page_number": 1,
        "image_order": 0,
        "data": data,
        "content_type": "image/png",
        "content_sha256": "abc123digest",
        "width_px": 120,
        "height_px": 80,
        "size_bytes": len(data),
        "alt_text": None,
        "nearby_text": "local nearby caption",
        "bbox_jsonb": None,
    }
    fields.update(overrides)
    return ExtractedEmbeddedImage(**fields)  # type: ignore[arg-type]


def _service(
    *,
    llm_text_enabled: bool = True,
    vision: object | None = None,
    repo: object | None = None,
) -> tuple[SourceImagePersistService, list[object]]:
    settings = Settings(
        ingest_source_image_extraction_enabled=True,
        ingest_source_image_llm_text_enabled=llm_text_enabled,
    )
    storage = AsyncMock()
    storage.put_object_from_local_file = AsyncMock()
    added: list[object] = []
    session = MagicMock()
    session.add = added.append
    session.flush = AsyncMock()
    if vision is None:
        vision = AsyncMock()
        vision.extract_image_text = AsyncMock(return_value="Systolic BP\nLine chart")
    svc = SourceImagePersistService(session, storage=storage, settings=settings, vision=vision)
    if repo is None:
        repo = AsyncMock()
        repo.list_pages_for_document = AsyncMock(return_value=[])
        repo.find_usable_alt_text_by_sha256 = AsyncMock(return_value=None)
    svc._repo = repo  # type: ignore[method-assign]
    return svc, added


@pytest.mark.asyncio
async def test_usable_document_alt_skips_llm_and_cache() -> None:
    image = _image(alt_text="Blood pressure staging chart")
    vision = AsyncMock()
    vision.extract_image_text = AsyncMock()
    repo = AsyncMock()
    repo.list_pages_for_document = AsyncMock(return_value=[])
    repo.find_usable_alt_text_by_sha256 = AsyncMock()
    svc, added = _service(vision=vision, repo=repo)
    with patch(
        "platform_service.services.source_image_persist_service.extract_embedded_images",
        return_value=[image],
    ):
        rows = await svc.extract_and_persist(
            source_document_id=uuid4(),
            source_path="/tmp/fig.pdf",
            source_type="pdf",
        )
    assert len(rows) == 1
    assert added[0].alt_text == "Blood pressure staging chart"
    assert added[0].nearby_text == "local nearby caption"
    vision.extract_image_text.assert_not_awaited()
    repo.find_usable_alt_text_by_sha256.assert_not_awaited()


@pytest.mark.asyncio
async def test_placeholder_alt_reuses_sha256_and_keeps_local_nearby() -> None:
    image = _image(alt_text="Picture 3")
    vision = AsyncMock()
    vision.extract_image_text = AsyncMock()
    repo = AsyncMock()
    repo.list_pages_for_document = AsyncMock(return_value=[])
    repo.find_usable_alt_text_by_sha256 = AsyncMock(return_value="Cached chart labels")
    svc, added = _service(vision=vision, repo=repo)
    with patch(
        "platform_service.services.source_image_persist_service.extract_embedded_images",
        return_value=[image],
    ):
        await svc.extract_and_persist(
            source_document_id=uuid4(),
            source_path="/tmp/fig.pdf",
            source_type="pdf",
        )
    assert added[0].alt_text == "Cached chart labels"
    assert added[0].nearby_text == "local nearby caption"
    vision.extract_image_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_miss_calls_llm_once() -> None:
    image = _image(alt_text=None)
    vision = AsyncMock()
    vision.extract_image_text = AsyncMock(return_value="mmHg\nBar chart")
    repo = AsyncMock()
    repo.list_pages_for_document = AsyncMock(return_value=[])
    repo.find_usable_alt_text_by_sha256 = AsyncMock(return_value=None)
    svc, added = _service(vision=vision, repo=repo)
    with patch(
        "platform_service.services.source_image_persist_service.extract_embedded_images",
        return_value=[image],
    ):
        await svc.extract_and_persist(
            source_document_id=uuid4(),
            source_path="/tmp/fig.pdf",
            source_type="pdf",
        )
    vision.extract_image_text.assert_awaited_once()
    assert added[0].alt_text == "mmHg\nBar chart"


@pytest.mark.asyncio
async def test_llm_exception_still_inserts_row() -> None:
    image = _image(alt_text="Picture 3")
    vision = AsyncMock()
    vision.extract_image_text = AsyncMock(side_effect=VisionExtractionError("boom"))
    svc, added = _service(vision=vision)
    with patch(
        "platform_service.services.source_image_persist_service.extract_embedded_images",
        return_value=[image],
    ):
        rows = await svc.extract_and_persist(
            source_document_id=uuid4(),
            source_path="/tmp/fig.pdf",
            source_type="pdf",
        )
    assert len(rows) == 1
    assert added[0].alt_text is None
    assert added[0].nearby_text == "local nearby caption"


@pytest.mark.asyncio
async def test_flag_off_never_calls_llm() -> None:
    image = _image()
    vision = AsyncMock()
    vision.extract_image_text = AsyncMock()
    svc, added = _service(llm_text_enabled=False, vision=vision)
    with patch(
        "platform_service.services.source_image_persist_service.extract_embedded_images",
        return_value=[image],
    ):
        await svc.extract_and_persist(
            source_document_id=uuid4(),
            source_path="/tmp/fig.pdf",
            source_type="pdf",
        )
    vision.extract_image_text.assert_not_awaited()
    assert added[0].alt_text is None


@pytest.mark.asyncio
async def test_flag_off_still_reuses_sha256() -> None:
    image = _image()
    vision = AsyncMock()
    vision.extract_image_text = AsyncMock()
    repo = AsyncMock()
    repo.list_pages_for_document = AsyncMock(return_value=[])
    repo.find_usable_alt_text_by_sha256 = AsyncMock(return_value="Prior alt")
    svc, added = _service(llm_text_enabled=False, vision=vision, repo=repo)
    with patch(
        "platform_service.services.source_image_persist_service.extract_embedded_images",
        return_value=[image],
    ):
        await svc.extract_and_persist(
            source_document_id=uuid4(),
            source_path="/tmp/fig.pdf",
            source_type="pdf",
        )
    vision.extract_image_text.assert_not_awaited()
    assert added[0].alt_text == "Prior alt"
