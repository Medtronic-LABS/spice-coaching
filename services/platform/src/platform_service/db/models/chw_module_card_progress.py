"""Per-card module viewing progress per CHW.

Tracks which cards (``module_card.id``) a CHW has viewed for a given
module version (``module.id``). When a module contains no quizzes and the CHW
has viewed all cards in the module, the module is marked completed in
``chw_module_completion``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_service.db.base import Base
from platform_service.db.models.mixins import TenantMixin


class CHWModuleCardProgress(TenantMixin, Base):
    __tablename__ = "chw_module_card_progress"
    __table_args__ = (
        PrimaryKeyConstraint(
            "chw_id",
            "module_id",
            "card_id",
            name="pk_chw_module_card_progress",
        ),
        Index("ix_chw_module_card_progress_chw_module", "chw_id", "module_id"),
    )

    chw_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("module.id", ondelete="CASCADE"),
        nullable=False,
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("module_card.id", ondelete="CASCADE"),
        nullable=False,
    )

    first_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
