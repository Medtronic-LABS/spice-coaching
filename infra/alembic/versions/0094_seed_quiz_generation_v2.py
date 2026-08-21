"""Seed quiz-generation prompt v2 (self-contained scenario stems).

Folds patient scenario into question text; omits case_setup on new writes;
deactivates v1.

Revision ID: 0094
Revises: 0093
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0094"
down_revision: str | None = "0093"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_PATH = Path(__file__).resolve().parents[3] / "seed" / "prompt_templates.json"
_TEMPLATE_ID = "quiz-generation"
_V2_VERSION = 2
_V1_VERSION = 1
_DEFAULT_TENANT_ID = 0


def upgrade() -> None:
    if not _SEED_PATH.exists():
        return
    rows = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    v2_row = next(
        (r for r in rows if r.get("template_id") == _TEMPLATE_ID and r.get("version") == _V2_VERSION),
        None,
    )
    if v2_row is None:
        return

    bind = op.get_bind()

    # Deactivate v1.
    bind.execute(
        sa.text(
            """
            UPDATE prompt_template
               SET status = 'inactive'
             WHERE tenant_id = :tenant_id
               AND template_id = :template_id
               AND version = :version
               AND variant_key IS NULL
            """
        ),
        {
            "tenant_id": _DEFAULT_TENANT_ID,
            "template_id": _TEMPLATE_ID,
            "version": _V1_VERSION,
        },
    )

    # Insert v2 only when not already present.
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
            "version": _V2_VERSION,
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
                    :required_variables,
                    :title,
                    :description,
                    :change_notes,
                    :status
                )
                """
            ),
            {
                "id": uuid.UUID(str(v2_row["id"])),
                "tenant_id": _DEFAULT_TENANT_ID,
                "template_id": _TEMPLATE_ID,
                "version": _V2_VERSION,
                "variant_key": None,
                "generation_type": v2_row["generation_type"],
                "system_prompt_template": v2_row["system_prompt_template"],
                "human_message_template": v2_row["human_message_template"],
                "required_variables": json.dumps(v2_row["required_variables"]),
                "title": v2_row["title"],
                "description": v2_row.get("description") or "",
                "change_notes": v2_row.get("change_notes") or "",
                "status": "active",
            },
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Remove v2.
    bind.execute(
        sa.text(
            """
            DELETE FROM prompt_template
             WHERE tenant_id = :tenant_id
               AND template_id = :template_id
               AND version = :version
               AND variant_key IS NULL
            """
        ),
        {
            "tenant_id": _DEFAULT_TENANT_ID,
            "template_id": _TEMPLATE_ID,
            "version": _V2_VERSION,
        },
    )

    # Re-activate v1.
    bind.execute(
        sa.text(
            """
            UPDATE prompt_template
               SET status = 'active'
             WHERE tenant_id = :tenant_id
               AND template_id = :template_id
               AND version = :version
               AND variant_key IS NULL
            """
        ),
        {
            "tenant_id": _DEFAULT_TENANT_ID,
            "template_id": _TEMPLATE_ID,
            "version": _V1_VERSION,
        },
    )
