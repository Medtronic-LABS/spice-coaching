"""Junction table for User to Upazila many-to-many relationship."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from platform_service.db.base import Base


class UserUpazila(Base):
    __tablename__ = "user_upazila"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    upazila_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("upazila.id", ondelete="CASCADE"),
        primary_key=True,
    )
