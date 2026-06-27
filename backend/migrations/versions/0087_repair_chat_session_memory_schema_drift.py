"""repair chat session memory schema drift

Revision ID: 0087_repair_chat_session_memory_schema_drift
Revises: 0086_repair_shared_memory_schema_drift
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0087_repair_chat_session_memory_schema_drift"
down_revision = "0086_repair_shared_memory_schema_drift"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    _add_column_if_missing("chat_sessions", sa.Column("context_summary", sa.Text(), nullable=True))
    _add_column_if_missing("chat_sessions", sa.Column("context_facts_json", mysql.JSON(), nullable=True))
    _add_column_if_missing(
        "chat_sessions",
        sa.Column("summary_seq_no", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "chat_sessions",
        sa.Column("context_updated_at", mysql.DATETIME(fsp=3), nullable=True),
    )
    if _has_column("chat_sessions", "summary_seq_no"):
        op.alter_column("chat_sessions", "summary_seq_no", server_default=None)


def downgrade() -> None:
    pass
