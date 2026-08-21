"""Seed coaching-rag prompt template v2 (graceful insufficient-context).

Revision ID: 0084
Revises: 0083
Create Date: 2026-08-15
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0084"
down_revision: str | None = "0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_PATH = Path(__file__).resolve().parents[3] / "seed" / "prompt_templates.json"
_TEMPLATE_ID = "coaching-rag"
_DEFAULT_TENANT_ID = 0
_V1_VERSION = 1


def upgrade() -> None:
    if not _SEED_PATH.exists():
        return
    rows = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    row = next((r for r in rows if r.get("template_id") == _TEMPLATE_ID), None)
    if row is None:
        return

    version = int(row["version"])
    row_id = uuid.UUID(str(row["id"]))
    bind = op.get_bind()

    existing = bind.execute(
        sa.text(
            """
            SELECT 1 FROM prompt_template
            WHERE tenant_id = :tenant_id
              AND template_id = :template_id
              AND version = :version
              AND variant_key IS NULL
            LIMIT 1
            """
        ),
        {
            "tenant_id": _DEFAULT_TENANT_ID,
            "template_id": _TEMPLATE_ID,
            "version": version,
        },
    ).first()

    if existing is None:
        bind.execute(
            sa.text(
                """
                INSERT INTO prompt_template (
                    id,
                    tenant_id,
                    template_id,
                    version,
                    variant_key,
                    generation_type,
                    system_prompt_template,
                    human_message_template,
                    required_variables,
                    title,
                    description,
                    change_notes,
                    status
                ) VALUES (
                    :id,
                    :tenant_id,
                    :template_id,
                    :version,
                    :variant_key,
                    :generation_type,
                    :system_prompt_template,
                    :human_message_template,
                    CAST(:required_variables AS jsonb),
                    :title,
                    :description,
                    :change_notes,
                    :status
                )
                """
            ),
            {
                "id": row_id,
                "tenant_id": _DEFAULT_TENANT_ID,
                "template_id": row["template_id"],
                "version": version,
                "variant_key": row.get("variant_key"),
                "generation_type": row["generation_type"],
                "system_prompt_template": row["system_prompt_template"],
                "human_message_template": row["human_message_template"],
                "required_variables": json.dumps(row["required_variables"]),
                "title": row["title"],
                "description": row["description"],
                "change_notes": row["change_notes"],
                "status": "deprecated",
            },
        )

    bind.execute(
        sa.text(
            """
            UPDATE prompt_template
            SET status = 'deprecated', updated_at = NOW()
            WHERE template_id = :template_id
              AND status = 'active'
              AND id <> :id
            """
        ),
        {"template_id": _TEMPLATE_ID, "id": row_id},
    )
    bind.execute(
        sa.text(
            """
            UPDATE prompt_template
            SET status = 'active', updated_at = NOW()
            WHERE id = :id
            """
        ),
        {"id": row_id},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM prompt_template
            WHERE template_id = :template_id
              AND version = :version
            """
        ),
        {"template_id": _TEMPLATE_ID, "version": 2},
    )
    bind.execute(
        sa.text(
            """
            UPDATE prompt_template
            SET status = 'active', updated_at = NOW()
            WHERE template_id = :template_id
              AND version = :version
              AND variant_key IS NULL
            """
        ),
        {"template_id": _TEMPLATE_ID, "version": _V1_VERSION},
    )
