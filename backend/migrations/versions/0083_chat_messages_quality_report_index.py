"""add chat message index for quality report

Revision ID: 0083_chat_messages_quality_report_index
Revises: 0082_repair_meeting_conflict_governance_schema
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0083_chat_messages_quality_report_index"
down_revision = "0082_repair_meeting_conflict_governance_schema"
branch_labels = None
depends_on = None


INDEX_NAME = "idx_chat_messages_org_role_created"


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names() and any(
        index["name"] == index_name for index in inspector.get_indexes(table_name)
    )


def upgrade() -> None:
    if not _has_index("chat_messages", INDEX_NAME):
        op.create_index(INDEX_NAME, "chat_messages", ["org_id", "role", "created_at"])


def downgrade() -> None:
    if _has_index("chat_messages", INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="chat_messages")
