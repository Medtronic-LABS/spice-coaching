"""CHW earned-badge assignment — one row per (chw_id, badge_id)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_service.db.base import Base
from platform_service.db.models.mixins import TenantMixin


class CHWBadge(TenantMixin, Base):
    __tablename__ = "chw_badge"
    __table_args__ = (
        PrimaryKeyConstraint("chw_id", "badge_id", name="pk_chw_badge"),
        Index("ix_chw_badge_chw_id", "chw_id"),
        Index("ix_chw_badge_badge_id", "badge_id"),
    )

    chw_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    badge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("badge.id", ondelete="CASCADE"),
        nullable=False,
    )
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
