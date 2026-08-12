"""Shared SQLAlchemy column mixins for platform models."""

from __future__ import annotations

from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column


class TenantMixin:
    """Required SPICE-aligned tenant identifier on parent/root tables."""

    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
