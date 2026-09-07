"""Add module_card.local_embedding for local EmbeddingGemma retrieval eval.

Revision ID: 0102
Revises: 0101
Create Date: 2026-09-01

Parallel per-card corpus vectors generated via ai-runtime ``use_local=true``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0102"
down_revision: str | None = "0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE module_card ADD COLUMN IF NOT EXISTS local_embedding vector({_EMBEDDING_DIM})"
    )


def downgrade() -> None:
    op.drop_column("module_card", "local_embedding")
