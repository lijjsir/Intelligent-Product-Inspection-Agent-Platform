"""make prompt_version nullable in inspection_results

Revision ID: 0083
Revises: 0082
Create Date: 2026-06-26 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "inspection_results",
        "prompt_version",
        existing_type=sa.String(32),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "inspection_results",
        "prompt_version",
        existing_type=sa.String(32),
        nullable=False,
    )
