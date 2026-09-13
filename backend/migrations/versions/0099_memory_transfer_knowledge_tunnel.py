"""persist knowledge tunnel plans on memory transfers

Revision ID: 0099_memory_transfer_knowledge_tunnel
Revises: 0098_message_feedback_provenance
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision = "0099_memory_transfer_knowledge_tunnel"
down_revision = "0098_message_feedback_provenance"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade() -> None:
    columns = (
        sa.Column("mapping_plan_json", mysql.JSON(), nullable=True),
        sa.Column("mapping_version", sa.String(128), nullable=True),
        sa.Column("interpolation_strategy", sa.String(32), nullable=True),
    )
    for column in columns:
        if not _has_column("memory_transfer_logs", column.name):
            op.add_column("memory_transfer_logs", column)


def downgrade() -> None:
    for name in ("interpolation_strategy", "mapping_version", "mapping_plan_json"):
        if _has_column("memory_transfer_logs", name):
            op.drop_column("memory_transfer_logs", name)
