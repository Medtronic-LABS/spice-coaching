"""Shared SQLAlchemy column mixins for platform models."""

from __future__ import annotations

from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from platform_service.db.default_tenant import DEFAULT_TENANT_ID


class TenantMixin:
    """Required SPICE-aligned tenant identifier on parent/root tables.

    The column is NOT NULL with no server default (see migration 0058), so the
    ORM supplies ``DEFAULT_TENANT_ID`` when a create path does not thread a
    tenant — the same "unresolved tenant" sentinel that migration backfilled
    existing rows with. Write paths are typed ``tenant_id: int`` so a missing
    tenant is caught by the type checker rather than silently landing here.
    """

    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, default=DEFAULT_TENANT_ID)
