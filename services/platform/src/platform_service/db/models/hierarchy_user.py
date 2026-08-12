"""Org-hierarchy user rows (Area Manager → PO → Shastiya Kormi)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_service.db.base import Base
from platform_service.db.models.mixins import TenantMixin
from platform_service.db.models.upazila import Upazila

ROLE_AREA_MANAGER = "AREA_MANAGER"
ROLE_PO = "PO"
ROLE_SHASTIYA_KORMI = "SHASTIYA_KORMI"

HIERARCHY_ROLES = frozenset(
    {
        ROLE_AREA_MANAGER,
        ROLE_PO,
        ROLE_SHASTIYA_KORMI,
    }
)


class HierarchyUser(TenantMixin, Base):
    """Mapped to table ``users`` (avoids reserved-word ``user``)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('AREA_MANAGER', 'PO', 'SHASTIYA_KORMI')",
            name="ck_users_role",
        ),
        CheckConstraint(
            "(role = 'AREA_MANAGER' AND parent_id IS NULL) OR "
            "(role <> 'AREA_MANAGER' AND parent_id IS NOT NULL)",
            name="ck_users_parent_nullability",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    district_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("district.id", ondelete="CASCADE"),
        nullable=False,
    )
    upazilas: Mapped[list[Upazila]] = relationship(
        "Upazila",
        secondary="user_upazila",
        lazy="selectin",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(Text, nullable=False)
