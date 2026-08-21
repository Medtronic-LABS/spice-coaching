"""Index source_image.content_sha256 and seed vision-image-text prompt.

Revision ID: 0091
Revises: 0090
"""

import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0091"
down_revision: str | None = "0090"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_PATH = Path(__file__).resolve().parents[3] / "seed" / "prompt_templates.json"
_TEMPLATE_ID = "vision-image-text"
_DEFAULT_TENANT_ID = 0


def upgrade() -> None:
    op.create_index(
        "ix_source_image_content_sha256",
        "source_image",
        ["content_sha256"],
        postgresql_where=sa.text("alt_text IS NOT NULL"),
    )
    if not _SEED_PATH.exists():
        return
    rows = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    row = next((r for r in rows if r.get("template_id") == _TEMPLATE_ID), None)
    if row is None:
        return
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
            "template_id": row["template_id"],
            "version": int(row["version"]),
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
            "version": int(row["version"]),
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


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM prompt_template WHERE template_id = :template_id"),
        {"template_id": _TEMPLATE_ID},
    )
    op.drop_index("ix_source_image_content_sha256", table_name="source_image")
