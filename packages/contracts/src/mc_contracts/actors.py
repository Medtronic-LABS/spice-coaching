"""Shared actor / user reference DTOs for API responses."""

from __future__ import annotations

from pydantic import BaseModel


class UserActorRef(BaseModel):
    """Soft reference to a hierarchy user (`users.id`) resolved at read time.

    Stored columns hold only the bigint id with no FK. When the user row is
    missing, API fields typed as ``UserActorRef | None`` are ``None``.
    """

    id: int
    name: str
