"""Shared geography helpers for hierarchy user enrichment."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


class HasDistrictId(Protocol):
    district_id: int | None


def non_null_district_ids(users: Iterable[HasDistrictId]) -> set[int]:
    """Collect district ids from users, excluding null (e.g. SUPER_ADMIN rows)."""
    return {u.district_id for u in users if u.district_id is not None}
