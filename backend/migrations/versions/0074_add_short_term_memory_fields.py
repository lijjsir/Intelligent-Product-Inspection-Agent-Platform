"""add short-term memory fields

Revision ID: 0074_short_term_memory_fields
Revises: 0073
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0074_short_term_memory_fields"
down_revision = "0073"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(col["name"] == column_name for col in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if _has_table(table_name) and _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def upgrade():
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

    if not _has_table("graph_checkpoints"):
        op.create_table(
            "graph_checkpoints",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("thread_id", sa.String(256), nullable=False),
            sa.Column("checkpoint_ns", sa.String(256), nullable=False, server_default=""),
            sa.Column("checkpoint_id", sa.String(128), nullable=False),
            sa.Column("parent_checkpoint_id", sa.String(128), nullable=True),
            sa.Column("type", sa.String(64), nullable=False),
            sa.Column("checkpoint", mysql.LONGTEXT(), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index("graph_checkpoints", "ix_graph_checkpoints_thread_id"):
        op.create_index("ix_graph_checkpoints_thread_id", "graph_checkpoints", ["thread_id"])
    if not _has_index("graph_checkpoints", "idx_graph_checkpoints_thread_latest"):
        op.create_index(
            "idx_graph_checkpoints_thread_latest",
            "graph_checkpoints",
            ["thread_id", "checkpoint_ns", "id"],
        )


def downgrade():
    if _has_index("graph_checkpoints", "idx_graph_checkpoints_thread_latest"):
        op.drop_index("idx_graph_checkpoints_thread_latest", table_name="graph_checkpoints")
    if _has_index("graph_checkpoints", "ix_graph_checkpoints_thread_id"):
        op.drop_index("ix_graph_checkpoints_thread_id", table_name="graph_checkpoints")
    if _has_table("graph_checkpoints"):
        op.drop_table("graph_checkpoints")

    _drop_column_if_exists("chat_sessions", "context_updated_at")
    _drop_column_if_exists("chat_sessions", "summary_seq_no")
    _drop_column_if_exists("chat_sessions", "context_facts_json")
    _drop_column_if_exists("chat_sessions", "context_summary")
