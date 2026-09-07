"""Add module.local_embedding for local EmbeddingGemma retrieval eval.

Revision ID: 0101
Revises: 0100
Create Date: 2026-09-01

Parallel corpus vectors generated via ai-runtime ``use_local=true`` and used
by ``--method local_embedding`` in the RAG eval harness.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0101"
down_revision: str | None = "0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute(f"ALTER TABLE module ADD COLUMN IF NOT EXISTS local_embedding vector({_EMBEDDING_DIM})")


def downgrade() -> None:
    op.drop_column("module", "local_embedding")
