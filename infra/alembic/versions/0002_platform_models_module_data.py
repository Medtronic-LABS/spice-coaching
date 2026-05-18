"""Platform models module data (seed) — no-op.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-12

Original behaviour loaded a 2146-row BRAC/UHIS training content dump as
part of schema migration. Moved to ``seed/platform_models_module_data.sql``
so the public OSS repo does not auto-redistribute that content. Run
manually with ``psql -f seed/platform_models_module_data.sql`` after
confirming redistribution rights.

This migration is kept (rather than deleted) so the revision chain stays
contiguous and existing deployments that have already applied it do not
encounter a missing revision on the next ``alembic upgrade head``.
"""

# pylint: disable=no-member

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
