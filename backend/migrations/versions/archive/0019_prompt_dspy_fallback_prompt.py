"""add fallback prompt field to prompt dspy configs

Revision ID: 0019_prompt_dspy_fallback
Revises: 0018_quality_agent_runtime
Create Date: 2026-04-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "0019_prompt_dspy_fallback"
down_revision = "0018_quality_agent_runtime"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("prompt_dspy_configs", "fallback_prompt"):
        op.add_column("prompt_dspy_configs", sa.Column("fallback_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("prompt_dspy_configs", "fallback_prompt"):
        op.drop_column("prompt_dspy_configs", "fallback_prompt")
