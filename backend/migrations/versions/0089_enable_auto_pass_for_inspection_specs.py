"""enable auto pass for inspection specs

Revision ID: 0089_enable_auto_pass_for_inspection_specs
Revises: 0088_unify_inspection_spec_image_count
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0089_enable_auto_pass_for_inspection_specs"
down_revision = "0088_unify_inspection_spec_image_count"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("inspection_specs"):
        return
    op.execute("UPDATE inspection_specs SET auto_pass_enabled = 1 WHERE auto_pass_enabled <> 1 OR auto_pass_enabled IS NULL")


def downgrade() -> None:
    pass
