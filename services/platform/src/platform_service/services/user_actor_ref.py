"""Resolve soft user-id columns to ``UserActorRef`` for API responses."""

from __future__ import annotations

from typing import Any

from mc_contracts.actors import UserActorRef


def to_user_actor_ref(
    user_id: int | None,
    users_by_id: dict[int, Any] | None,
) -> UserActorRef | None:
    """Return a ``UserActorRef`` when ``user_id`` is present and found in ``users_by_id``.

    Missing ids (orphan soft refs) yield ``None`` — the stored bigint is kept in
    the database but not exposed as an actor DTO.
    """
    if user_id is None or users_by_id is None:
        return None
    user = users_by_id.get(user_id)
    if user is None:
        return None
    return UserActorRef(id=user.id, name=user.name)
