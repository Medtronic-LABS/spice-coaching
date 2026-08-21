"""Unit tests for source_image alt usability, clipping, and LLM parse."""

import pytest
from platform_service.services.image_alt_text import (
    clip_image_alt_text,
    is_usable_image_alt,
    parse_image_text_response,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, False),
        ("", False),
        ("   ", False),
        ("Picture 3", False),
        ("picture 3", False),
        ("Image 1", False),
        ("Graphic 12", False),
        ("Photo", False),
        ("Slide 2", False),
        ("Figure", False),
        ("BP chart", True),
        ("Hypertension staging diagram", True),
        ("Figure of fundal height", True),
    ],
)
def test_is_usable_image_alt(text: str | None, expected: bool) -> None:
    assert is_usable_image_alt(text) is expected


def test_clip_image_alt_preserves_newlines_and_caps() -> None:
    assert clip_image_alt_text("  BP  \n\n  chart  ") == "BP\nchart"
    long = "a" * 1200
    clipped = clip_image_alt_text(long, max_chars=10)
    assert clipped is not None
    assert len(clipped) == 10
    assert clipped.endswith("…")


def test_parse_labeled_blocks() -> None:
    raw = "VISIBLE_TEXT:\nSystolic BP\nDESCRIPTION:\nLine chart of blood pressure."
    assert parse_image_text_response(raw) == "Systolic BP\nLine chart of blood pressure."


def test_parse_description_only() -> None:
    raw = "VISIBLE_TEXT:\n\nDESCRIPTION:\nA photo of a clinic waiting room."
    assert parse_image_text_response(raw) == "A photo of a clinic waiting room."


def test_parse_json_visible_and_description() -> None:
    raw = '{"visible_text": "Axis: mmHg", "description": "Bar chart of cases."}'
    assert parse_image_text_response(raw) == "Axis: mmHg\nBar chart of cases."


def test_parse_fenced_plain_text() -> None:
    raw = "```\nVISIBLE_TEXT:\nLabel A\nDESCRIPTION:\nDiagram.\n```"
    assert parse_image_text_response(raw) == "Label A\nDiagram."


def test_parse_unlabeled_plain_text() -> None:
    assert parse_image_text_response("just a caption") == "just a caption"


def test_parse_empty() -> None:
    assert parse_image_text_response("  \n  ") == ""
