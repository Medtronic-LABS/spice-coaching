"""Formalize tenant_id as BIGINT NOT NULL on parent/root tables.

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-02

Converts UUID tenant_id columns to BIGINT NOT NULL, tightens assignment
tenant_id to NOT NULL, and adds tenant_id to previously untenanted root
tables. Existing NULL tenant_id values (and new columns on existing rows)
are backfilled to 0 via a temporary server default, then the default is
dropped. Downgrade is lossy (schema restore only).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Parent/root tables that already had UUID tenant_id.
_UUID_TENANT_TABLES: tuple[str, ...] = (
    "module",
    "behavioural_gap",
    "trigger_definition",
    "chw_behavioural_gap_state",
    "chw_module_completion",
    "chw_learning_point_event",
    "chw_module_quiz_progress",
    "chw_gap_telemetry_event",
    "chw_quiz_question_state",
    "chw_training_request",
    "chw_video_progress",
    "module_demand_summary",
    "module_creation_suggestion",
    "chat_frequent_question",
    "chat_feedback_summary",
)

# Roots that gain a new BIGINT tenant_id.
_NEW_TENANT_TABLES: tuple[str, ...] = (
    "module_family",
    "source_document",
    "file_upload",
    "ingest_batch",
    "badge",
    "attribution_event",
    "module_candidate_draft",
    "prompt_template",
    "config_threshold",
    "llm_call_cache",
)

_ZERO_SERVER_DEFAULT = sa.text("0")


def _add_bigint_tenant_id(table: str) -> None:
    """Add NOT NULL BIGINT tenant_id; existing rows get 0, then drop DEFAULT."""
    op.add_column(
        table,
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            server_default=_ZERO_SERVER_DEFAULT,
        ),
    )
    op.alter_column(table, "tenant_id", server_default=None)
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])


def _drop_uuid_tenant_indexes() -> None:
    op.drop_index("ix_module_creation_suggestion_tenant_date", table_name="module_creation_suggestion")
    op.drop_index("ix_module_demand_summary_tenant", table_name="module_demand_summary")
    op.execute(sa.text("DROP INDEX IF EXISTS uq_module_demand_summary_tenant"))
    op.execute(sa.text("DROP INDEX IF EXISTS uq_module_demand_summary_global"))
    op.drop_index("ix_chat_feedback_summary_tenant", table_name="chat_feedback_summary")
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chat_faq_tenant_rank"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chat_faq_tenant_updated"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_chw_training_request_tenant_submitted"))
    # Recreate uniqueness after type change; drop named unique first.
    op.drop_constraint("uq_chat_faq_tenant_question", "chat_frequent_question", type_="unique")


def _recreate_bigint_tenant_indexes() -> None:
    op.create_index(
        "ix_module_creation_suggestion_tenant_date",
        "module_creation_suggestion",
        ["tenant_id", "suggestion_date"],
    )
    op.create_index("ix_module_demand_summary_tenant", "module_demand_summary", ["tenant_id"])
    op.create_index(
        "ix_chat_faq_tenant_rank",
        "chat_frequent_question",
        ["tenant_id", "rank"],
    )
    op.create_index(
        "ix_chat_faq_tenant_updated",
        "chat_frequent_question",
        ["tenant_id", "updated_at"],
    )
    op.create_index(
        "ix_chw_training_request_tenant_submitted",
        "chw_training_request",
        ["tenant_id", "submitted_at"],
    )
    op.create_unique_constraint(
        "uq_chat_faq_tenant_question",
        "chat_frequent_question",
        ["tenant_id", "normalized_question"],
    )
    op.create_index(
        "ix_chat_feedback_summary_tenant",
        "chat_feedback_summary",
        ["tenant_id"],
        unique=True,
    )


def upgrade() -> None:
    _drop_uuid_tenant_indexes()

    for table in _UUID_TENANT_TABLES:
        op.drop_column(table, "tenant_id")
        _add_bigint_tenant_id(table)

    # Assignment tables: already BigInteger; backfill NULLs then tighten NOT NULL.
    op.drop_constraint("uq_module_assignment_tenant", "chw_module_assignment", type_="unique")
    op.execute(sa.text("UPDATE chw_module_assignment SET tenant_id = 0 WHERE tenant_id IS NULL"))
    op.alter_column("chw_module_assignment", "tenant_id", existing_type=sa.BigInteger(), nullable=False)
    op.create_index(
        "uq_module_assignment_tenant",
        "chw_module_assignment",
        ["module_id", "tenant_id"],
        unique=True,
        postgresql_where=sa.text("assignment_type = 'group'"),
    )

    op.drop_constraint("uq_video_assignment_tenant", "chw_video_assignment", type_="unique")
    op.execute(sa.text("UPDATE chw_video_assignment SET tenant_id = 0 WHERE tenant_id IS NULL"))
    op.alter_column("chw_video_assignment", "tenant_id", existing_type=sa.BigInteger(), nullable=False)
    op.create_index(
        "uq_video_assignment_tenant",
        "chw_video_assignment",
        ["source_document_id", "tenant_id"],
        unique=True,
        postgresql_where=sa.text("assignment_type = 'group'"),
    )

    # Retarget global uniques before adding tenant_id.
    op.drop_constraint("module_family_module_code_key", "module_family", type_="unique")
    op.drop_constraint("config_threshold_key_key", "config_threshold", type_="unique")
    op.drop_constraint("llm_call_cache_input_hash_key", "llm_call_cache", type_="unique")
    op.drop_constraint("uq_prompt_template_id_variant_version", "prompt_template", type_="unique")

    for table in _NEW_TENANT_TABLES:
        _add_bigint_tenant_id(table)

    op.create_unique_constraint(
        "uq_module_family_tenant_code",
        "module_family",
        ["tenant_id", "module_code"],
    )
    op.create_unique_constraint(
        "uq_config_threshold_tenant_key",
        "config_threshold",
        ["tenant_id", "key"],
    )
    op.create_unique_constraint(
        "uq_llm_call_cache_tenant_hash",
        "llm_call_cache",
        ["tenant_id", "input_hash"],
    )
    op.create_unique_constraint(
        "uq_prompt_template_tenant_id_variant_version",
        "prompt_template",
        ["tenant_id", "template_id", "variant_key", "version"],
    )

    _recreate_bigint_tenant_indexes()


def downgrade() -> None:
    op.drop_constraint("uq_prompt_template_tenant_id_variant_version", "prompt_template", type_="unique")
    op.drop_constraint("uq_llm_call_cache_tenant_hash", "llm_call_cache", type_="unique")
    op.drop_constraint("uq_config_threshold_tenant_key", "config_threshold", type_="unique")
    op.drop_constraint("uq_module_family_tenant_code", "module_family", type_="unique")

    for table in _NEW_TENANT_TABLES:
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")

    op.create_unique_constraint(
        "uq_prompt_template_id_variant_version",
        "prompt_template",
        ["template_id", "variant_key", "version"],
    )
    op.create_unique_constraint("llm_call_cache_input_hash_key", "llm_call_cache", ["input_hash"])
    op.create_unique_constraint("config_threshold_key_key", "config_threshold", ["key"])
    op.create_unique_constraint("module_family_module_code_key", "module_family", ["module_code"])

    op.drop_index("uq_video_assignment_tenant", table_name="chw_video_assignment")
    op.alter_column("chw_video_assignment", "tenant_id", existing_type=sa.BigInteger(), nullable=True)
    op.create_unique_constraint(
        "uq_video_assignment_tenant",
        "chw_video_assignment",
        ["source_document_id", "tenant_id"],
    )

    op.drop_index("uq_module_assignment_tenant", table_name="chw_module_assignment")
    op.alter_column("chw_module_assignment", "tenant_id", existing_type=sa.BigInteger(), nullable=True)
    op.create_unique_constraint(
        "uq_module_assignment_tenant",
        "chw_module_assignment",
        ["module_id", "tenant_id"],
    )

    # Tear down BIGINT indexes that replace UUID-era ones.
    op.drop_index("ix_chw_training_request_tenant_submitted", table_name="chw_training_request")
    op.drop_index("ix_chat_faq_tenant_updated", table_name="chat_frequent_question")
    op.drop_index("ix_chat_faq_tenant_rank", table_name="chat_frequent_question")
    op.drop_constraint("uq_chat_faq_tenant_question", "chat_frequent_question", type_="unique")
    op.drop_index("ix_chat_feedback_summary_tenant", table_name="chat_feedback_summary")
    op.drop_constraint("uq_module_demand_summary_tenant", "module_demand_summary", type_="unique")
    op.drop_index("ix_module_demand_summary_tenant", table_name="module_demand_summary")
    op.drop_index("ix_module_creation_suggestion_tenant_date", table_name="module_creation_suggestion")

    for table in _UUID_TENANT_TABLES:
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
        nullable = table not in ("chat_frequent_question", "chat_feedback_summary")
        op.add_column(
            table,
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=nullable),
        )

    op.create_index(
        "ix_module_creation_suggestion_tenant_date",
        "module_creation_suggestion",
        ["tenant_id", "suggestion_date"],
    )
    op.create_index("ix_module_demand_summary_tenant", "module_demand_summary", ["tenant_id"])
    op.create_index(
        "uq_module_demand_summary_tenant",
        "module_demand_summary",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "uq_module_demand_summary_global",
        "module_demand_summary",
        [sa.text("(tenant_id IS NULL)")],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.create_index(
        "ix_chat_feedback_summary_tenant",
        "chat_feedback_summary",
        ["tenant_id"],
        unique=True,
    )
    op.create_unique_constraint(
        "uq_chat_faq_tenant_question",
        "chat_frequent_question",
        ["tenant_id", "normalized_question"],
    )
    op.create_index(
        "ix_chat_faq_tenant_rank",
        "chat_frequent_question",
        ["tenant_id", "rank"],
    )
    op.create_index(
        "ix_chat_faq_tenant_updated",
        "chat_frequent_question",
        ["tenant_id", "updated_at"],
    )
    op.create_index(
        "ix_chw_training_request_tenant_submitted",
        "chw_training_request",
        ["tenant_id", "submitted_at"],
    )
