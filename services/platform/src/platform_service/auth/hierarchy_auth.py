"""Post-SPICE hierarchy id/role binding for authenticated principals."""

from __future__ import annotations

import logging

from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_context import SpiceUserContext
from platform_service.db.repositories.hierarchy_repository import HierarchyRepository

logger = logging.getLogger(__name__)


def _spice_role_names(user: SpiceUserContext) -> set[str]:
    return {(role.name or "").strip() for role in user.roles if role.name}


async def enforce_hierarchy_principal(
    session: AsyncSession,
    user: SpiceUserContext,
) -> None:
    """Require hierarchy row id + exact role match unless SUPER/JOB user.

    Raises ``AppError`` with ``hierarchy_auth_failed`` (403) on failure.
    """
    if user.is_super_user or user.is_job_user:
        return

    if user.id is None:
        raise AppError(
            ErrorCode.HIERARCHY_AUTH_FAILED.value,
            "authenticated user has no id for hierarchy lookup",
            status=403,
        )

    hierarchy_user = await HierarchyRepository(session).get_user_by_id(user.id)
    if hierarchy_user is None:
        logger.warning(
            "hierarchy auth failed: user_id=%s missing from users table",
            user.id,
        )
        raise AppError(
            ErrorCode.HIERARCHY_AUTH_FAILED.value,
            f"hierarchy user {user.id} not found",
            status=403,
        )

    token_roles = _spice_role_names(user)
    if hierarchy_user.role not in token_roles:
        logger.warning(
            "hierarchy auth failed: user_id=%s hierarchy_role=%s token_roles=%s",
            user.id,
            hierarchy_user.role,
            sorted(token_roles),
        )
        raise AppError(
            ErrorCode.HIERARCHY_AUTH_FAILED.value,
            (
                f"hierarchy role {hierarchy_user.role} does not match "
                f"authenticated roles {sorted(token_roles)}"
            ),
            status=403,
        )
