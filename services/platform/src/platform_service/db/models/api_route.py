"""HTTP API route catalog and role→route access grants."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity, Text
from sqlalchemy.orm import Mapped, mapped_column

from platform_service.db.base import Base


class ApiRoute(Base):
    __tablename__ = "api_route"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
    )
    path_template: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class RoleRouteAccess(Base):
    __tablename__ = "role_route_access"

    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("role.id", ondelete="CASCADE"),
        primary_key=True,
    )
    api_route_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("api_route.id", ondelete="CASCADE"),
        primary_key=True,
    )
