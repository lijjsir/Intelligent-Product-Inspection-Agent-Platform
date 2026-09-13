"""capture answer provenance on message feedback

Revision ID: 0098_message_feedback_provenance
Revises: 0097_normalize_deleted_transfer_statuses
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision = "0098_message_feedback_provenance"
down_revision = "0097_normalize_deleted_transfer_statuses"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_column("message_feedbacks", "metadata_json"):
        op.add_column(
            "message_feedbacks",
            sa.Column("metadata_json", mysql.JSON(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("message_feedbacks", "metadata_json"):
        op.drop_column("message_feedbacks", "metadata_json")
