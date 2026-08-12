"""Shared predicates for module admin availability."""

from __future__ import annotations

from sqlalchemy import ColumnElement

from platform_service.db.models.module import Module

LIFECYCLE_PUBLISHED = "published"
LIFECYCLE_DEACTIVATED = "deactivated"
LIFECYCLE_RETIRED = "retired"
LIFECYCLE_DRAFT = "draft"
LIFECYCLE_REVIEW_PENDING = "review_pending"
VALID_LIFECYCLE_STATUSES = frozenset(
    {
        LIFECYCLE_DRAFT,
        LIFECYCLE_PUBLISHED,
        LIFECYCLE_RETIRED,
        LIFECYCLE_DEACTIVATED,
        LIFECYCLE_REVIEW_PENDING,
    }
)
# Hidden from default admin module lists unless explicitly filtered.
DEFAULT_EXCLUDED_LIFECYCLE_STATUSES = frozenset({LIFECYCLE_RETIRED, LIFECYCLE_DEACTIVATED})


def is_training_module_family() -> ColumnElement[bool]:
    """True when a module family participates in CHW training workflows."""
    return Module.chatbot_faqs_only.is_(False)
