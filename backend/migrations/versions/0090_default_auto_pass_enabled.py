"""default auto pass enabled

Revision ID: 0090_default_auto_pass_enabled
Revises: 0089_enable_auto_pass_for_inspection_specs
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0090_default_auto_pass_enabled"
down_revision = "0089_enable_auto_pass_for_inspection_specs"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("inspection_specs", "auto_pass_enabled"):
        return
    op.execute("ALTER TABLE inspection_specs MODIFY auto_pass_enabled TINYINT(1) NOT NULL DEFAULT 1")


def downgrade() -> None:
    pass
