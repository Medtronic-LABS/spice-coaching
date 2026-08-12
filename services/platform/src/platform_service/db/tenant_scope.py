"""Shared tenant scoping helpers for repository queries."""

from __future__ import annotations

from sqlalchemy import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute


def tenant_scope_filter(
    column: InstrumentedAttribute[int],
    tenant_id: int,
) -> ColumnElement[bool]:
    """Match rows belonging to ``tenant_id`` (exact equality; no shared-NULL scope)."""
    return column == tenant_id
