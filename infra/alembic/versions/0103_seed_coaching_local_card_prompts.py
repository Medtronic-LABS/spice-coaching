"""Seed coaching-local-card-rag and coaching-local-card-chat-route prompts.

Revision ID: 0103
Revises: 0102
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0103"
down_revision: str | None = "0102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_PATH = Path(__file__).resolve().parents[3] / "seed" / "prompt_templates.json"
_TEMPLATE_IDS = ("coaching-local-card-rag", "coaching-local-card-chat-route")
_DEFAULT_TENANT_ID = 0


def _seed_row(bind: sa.Connection, row: dict[str, object]) -> None:
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
            "template_id": row["template_id"],
            "version": int(row["version"]),  # type: ignore[arg-type]
        },
    ).first()
    if existing is not None:
        return
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
            "id": uuid.UUID(str(row["id"])),
            "tenant_id": _DEFAULT_TENANT_ID,
            "template_id": row["template_id"],
            "version": int(row["version"]),  # type: ignore[arg-type]
            "variant_key": row.get("variant_key"),
            "generation_type": row["generation_type"],
            "system_prompt_template": row["system_prompt_template"],
            "human_message_template": row["human_message_template"],
            "required_variables": json.dumps(row["required_variables"]),
            "title": row["title"],
            "description": row["description"],
            "change_notes": row["change_notes"],
            "status": row["status"],
        },
    )


def upgrade() -> None:
    if not _SEED_PATH.exists():
        return
    rows = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    bind = op.get_bind()
    for template_id in _TEMPLATE_IDS:
        row = next((r for r in rows if r.get("template_id") == template_id), None)
        if row is None:
            continue
        _seed_row(bind, row)


def downgrade() -> None:
    bind = op.get_bind()
    for template_id in _TEMPLATE_IDS:
        bind.execute(
            sa.text("DELETE FROM prompt_template WHERE template_id = :template_id"),
            {"template_id": template_id},
        )
