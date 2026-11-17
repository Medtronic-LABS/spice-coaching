"""Tracked paths must stay distinct on case-insensitive filesystems (macOS, Windows)."""

from __future__ import annotations

import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_paths() -> list[str]:
    if shutil.which("git") is None or not (_REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=True,
    )
    return [path for path in result.stdout.decode().split("\0") if path]


def test_no_tracked_paths_differ_only_by_case() -> None:
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for path in _tracked_paths():
        groups[path.casefold()].append(path)
    collisions = sorted(paths for paths in groups.values() if len(paths) > 1)
    assert collisions == [], f"paths that collide on case-insensitive filesystems: {collisions}"
