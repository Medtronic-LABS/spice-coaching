"""Post-SPICE hierarchy id/role binding for authenticated principals."""

from __future__ import annotations

import logging

from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_context import SpiceUserContext
from platform_service.auth.tenant_context import selected_tenant_from_user
from platform_service.db.models.hierarchy_user import ROLE_SUPER_ADMIN
from platform_service.db.repositories.hierarchy_repository import HierarchyRepository

logger = logging.getLogger(__name__)

_DEFAULT_SUPER_ADMIN_NAME = "Admin"


def _spice_role_names(user: SpiceUserContext) -> set[str]:
    return {(role.name or "").strip() for role in user.roles if role.name}


def _needs_super_admin_ensure(user: SpiceUserContext) -> bool:
    return user.is_super_user or user.is_job_user or ROLE_SUPER_ADMIN in _spice_role_names(user)


def _display_name(user: SpiceUserContext) -> str:
    parts = [p for p in (user.first_name, user.last_name) if p and p.strip()]
    if parts:
        return " ".join(p.strip() for p in parts)
    if user.username and user.username.strip():
        return user.username.strip()
    return _DEFAULT_SUPER_ADMIN_NAME


async def _ensure_super_admin_row(session: AsyncSession, user: SpiceUserContext) -> None:
    if user.id is None:
        raise AppError(
            ErrorCode.HIERARCHY_AUTH_FAILED.value,
            "authenticated user has no id for hierarchy lookup",
            status=403,
        )
    tenant_id = selected_tenant_from_user(user)
    if tenant_id is None:
        raise AppError(
            ErrorCode.HIERARCHY_AUTH_FAILED.value,
            "authenticated user has no country.tenantId for hierarchy provision",
            status=403,
        )

    repo = HierarchyRepository(session)
    if await repo.get_user_by_id(user.id) is not None:
        return

    try:
        await repo.ensure_super_admin_user(
            user_id=user.id,
            name=_display_name(user),
            tenant_id=tenant_id,
        )
    except IntegrityError:
        await session.rollback()
        # Concurrent first request already inserted the row.
        if await repo.get_user_by_id(user.id) is None:
            raise


async def enforce_hierarchy_principal(
    session: AsyncSession,
    user: SpiceUserContext,
) -> int | None:
    """Require hierarchy row id + exact role match unless SUPER/JOB user.

    Auto-provisions a root ``SUPER_ADMIN`` row (null district, no parent) when
    the principal is SUPER_USER, JOB_USER, or has token role SUPER_ADMIN and
    the row is missing. Existing rows are never updated.

    Returns the hierarchy ``role_id`` for authorization, or ``None`` when the
    principal bypasses hierarchy binding (SUPER/JOB).

    Raises ``AppError`` with ``hierarchy_auth_failed`` (403) on failure.
    """
    if _needs_super_admin_ensure(user):
        await _ensure_super_admin_row(session, user)

    if user.is_super_user or user.is_job_user:
        return None

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

    return hierarchy_user.role_id
