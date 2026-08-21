"""Org-hierarchy role catalog (AREA_MANAGER, PO, SHASTIYA_KORMI, SUPER_ADMIN, …)."""

from __future__ import annotations

from sqlalchemy import BigInteger, Identity, Text
from sqlalchemy.orm import Mapped, mapped_column

from platform_service.db.base import Base


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
