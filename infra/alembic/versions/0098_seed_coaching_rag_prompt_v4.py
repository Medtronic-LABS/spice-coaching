"""Seed coaching-rag prompt template v4 (multi-module synthesis).

Revision ID: 0098
Revises: 0097
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0098"
down_revision: str | None = "0097"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_PATH = Path(__file__).resolve().parents[3] / "seed" / "prompt_templates.json"
_TEMPLATE_ID = "coaching-rag"
_V4_VERSION = 4
_V3_VERSION = 3
_DEFAULT_TENANT_ID = 0


def upgrade() -> None:
    if not _SEED_PATH.exists():
        return
    rows = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    v4_row = next(
        (r for r in rows if r.get("template_id") == _TEMPLATE_ID and r.get("version") == _V4_VERSION),
        None,
    )
    if v4_row is None:
        return

    bind = op.get_bind()
    row_id = uuid.UUID(str(v4_row["id"]))

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
            "version": _V4_VERSION,
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
                "template_id": v4_row["template_id"],
                "version": _V4_VERSION,
                "variant_key": v4_row.get("variant_key"),
                "generation_type": v4_row["generation_type"],
                "system_prompt_template": v4_row["system_prompt_template"],
                "human_message_template": v4_row["human_message_template"],
                "required_variables": json.dumps(v4_row["required_variables"]),
                "title": v4_row["title"],
                "description": v4_row["description"],
                "change_notes": v4_row["change_notes"],
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
        {"template_id": _TEMPLATE_ID, "version": _V4_VERSION},
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
        {"template_id": _TEMPLATE_ID, "version": _V3_VERSION},
    )
