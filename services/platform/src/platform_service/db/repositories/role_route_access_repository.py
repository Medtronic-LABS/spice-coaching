"""Load role→route path-template grants from Postgres."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.api_route import ApiRoute, RoleRouteAccess


class RoleRouteAccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_path_templates_for_role(self, role_id: int) -> list[str]:
        """Return path templates granted to ``role_id`` (unordered)."""
        stmt = (
            select(ApiRoute.path_template)
            .join(RoleRouteAccess, RoleRouteAccess.api_route_id == ApiRoute.id)
            .where(RoleRouteAccess.role_id == role_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_path_templates(self) -> list[str]:
        """Return every catalogued path template."""
        result = await self._session.execute(select(ApiRoute.path_template))
        return list(result.scalars().all())
