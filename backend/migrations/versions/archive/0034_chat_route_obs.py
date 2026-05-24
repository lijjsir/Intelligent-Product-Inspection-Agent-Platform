"""add chat route observability fields

Revision ID: 0034_chat_route_obs
Revises: 0033_agent_route_logs
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0034_chat_route_obs"
down_revision = "0033_agent_route_logs"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _drop_column_if_present(table_name: str, column_name: str) -> None:
    if column_name in _columns(table_name):
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    _add_column_if_missing("agent_route_logs", sa.Column("sub_route", sa.String(length=64), nullable=True))
    _add_column_if_missing("agent_route_logs", sa.Column("fallback_agent", sa.String(length=64), nullable=True))
    _add_column_if_missing(
        "agent_route_logs",
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing("agent_route_logs", sa.Column("signals_json", mysql.JSON(), nullable=True))
    _add_column_if_missing("agent_route_logs", sa.Column("model_output_json", mysql.JSON(), nullable=True))
    _add_column_if_missing(
        "agent_route_logs",
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    _add_column_if_missing("rag_query_logs", sa.Column("agent_name", sa.String(length=64), nullable=True))
    _add_column_if_missing("rag_query_logs", sa.Column("sub_route", sa.String(length=64), nullable=True))
    _add_column_if_missing("rag_query_logs", sa.Column("trace_id", sa.String(length=128), nullable=True))
    _add_column_if_missing("rag_query_logs", sa.Column("top_score", sa.Numeric(8, 6), nullable=True))


def downgrade() -> None:
    for column_name in (
        "top_score",
        "trace_id",
        "sub_route",
        "agent_name",
    ):
        _drop_column_if_present("rag_query_logs", column_name)
    for column_name in (
        "latency_ms",
        "model_output_json",
        "signals_json",
        "requires_confirmation",
        "fallback_agent",
        "sub_route",
    ):
        _drop_column_if_present("agent_route_logs", column_name)
