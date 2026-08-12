"""Unit tests for video frame sampling helpers."""

from __future__ import annotations

from platform_service.workers.extractors.video_frame_sampler import (
    TimeRange,
    append_visual_section,
    format_visual_heading,
    plan_frame_timestamps,
)


def test_plan_frame_timestamps_interval_within_chunk() -> None:
    stamps = plan_frame_timestamps(
        [TimeRange(0, 120_000)],
        interval_ms=30_000,
        max_frames=40,
    )
    assert stamps == [0, 30_000, 60_000, 90_000]


def test_plan_frame_timestamps_respects_max_frames() -> None:
    stamps = plan_frame_timestamps(
        [TimeRange(0, 120_000), TimeRange(120_000, 240_000)],
        interval_ms=30_000,
        max_frames=5,
    )
    assert stamps == [0, 30_000, 60_000, 90_000, 120_000]


def test_plan_frame_timestamps_short_chunk_gets_start() -> None:
    stamps = plan_frame_timestamps(
        [TimeRange(0, 10_000)],
        interval_ms=30_000,
        max_frames=40,
    )
    assert stamps == [0]


def test_plan_frame_timestamps_empty_when_max_zero() -> None:
    assert plan_frame_timestamps([TimeRange(0, 60_000)], interval_ms=30_000, max_frames=0) == []


def test_format_visual_heading() -> None:
    assert format_visual_heading(90_000) == "## Visual (t=01:30)"
    assert format_visual_heading(3_661_000) == "## Visual (t=1:01:01)"


def test_append_visual_section_skips_empty() -> None:
    base = "# Transcript (chunk 1)\n\nHello"
    assert append_visual_section(base, start_ms=0, vision_markdown="  ") == base


def test_append_visual_section_merges() -> None:
    base = "# Transcript (chunk 1)\n\nHello"
    out = append_visual_section(base, start_ms=30_000, vision_markdown="A slide about BP")
    assert "## Visual (t=00:30)" in out
    assert "A slide about BP" in out
    assert out.startswith("# Transcript (chunk 1)")
