"""Org-hierarchy user rows (Area Manager → PO → Shastiya Kormi)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_service.db.base import Base
from platform_service.db.models.mixins import TenantMixin
from platform_service.db.models.role import Role
from platform_service.db.models.upazila import Upazila
from platform_service.db.models.user_upazila import UserUpazila  # noqa: F401 — used in relationship joins

ROLE_AREA_MANAGER = "AREA_MANAGER"
ROLE_PO = "PO"
ROLE_SHASTIYA_KORMI = "SHASTIYA_KORMI"
ROLE_SUPER_ADMIN = "SUPER_ADMIN"

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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("role.id"),
        nullable=False,
    )
    role_row: Mapped[Role] = relationship(Role, lazy="selectin")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    district_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("district.id", ondelete="CASCADE"),
        nullable=True,
    )
    upazilas: Mapped[list[Upazila]] = relationship(
        "Upazila",
        secondary="user_upazila",
        # Soft user_id on junction (no FK to users); spell joins explicitly.
        primaryjoin="HierarchyUser.id == foreign(UserUpazila.user_id)",
        secondaryjoin="Upazila.id == foreign(UserUpazila.upazila_id)",
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
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    @property
    def role(self) -> str:
        """Stable role code from the ``role`` lookup table (API-facing string)."""
        return self.role_row.code
