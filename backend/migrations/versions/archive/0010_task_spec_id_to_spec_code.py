"""rename inspection_tasks.spec_id to spec_code

Revision ID: 0010_task_spec_id_to_spec_code
Revises: 0009_model_configs_add_deleted_at
Create Date: 2026-03-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_task_spec_id_to_spec_code"
down_revision = "0009_model_cfg_deleted_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("inspection_tasks")}
    if "spec_id" in columns and "spec_code" not in columns:
        op.alter_column(
            "inspection_tasks",
            "spec_id",
            new_column_name="spec_code",
            existing_type=sa.String(length=64),
            existing_nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("inspection_tasks")}
    if "spec_code" in columns and "spec_id" not in columns:
        op.alter_column(
            "inspection_tasks",
            "spec_code",
            new_column_name="spec_id",
            existing_type=sa.String(length=64),
            existing_nullable=False,
        )
