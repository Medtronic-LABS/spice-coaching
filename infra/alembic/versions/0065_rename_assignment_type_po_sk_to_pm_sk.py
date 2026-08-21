"""Rename assignment_type po_sk → pm_sk on module and video assignments.

Revision ID: 0065
Revises: 0064
Create Date: 2026-08-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0065"
down_revision: str | None = "0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE chw_module_assignment SET assignment_type = 'pm_sk' WHERE assignment_type = 'po_sk'"
    )
    op.execute(
        "UPDATE chw_video_assignment SET assignment_type = 'pm_sk' WHERE assignment_type = 'po_sk'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE chw_module_assignment SET assignment_type = 'po_sk' WHERE assignment_type = 'pm_sk'"
    )
    op.execute(
        "UPDATE chw_video_assignment SET assignment_type = 'po_sk' WHERE assignment_type = 'pm_sk'"
    )
