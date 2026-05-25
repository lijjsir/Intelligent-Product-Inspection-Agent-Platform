"""expand alert_events and rag_query_logs idempotency key to 512

Revision ID: 0070
Revises: 0069
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_length(table_name: str, column_name: str) -> int | None:
    if not _has_table(table_name):
        return None
    for column in _inspector().get_columns(table_name):
        if column["name"] == column_name:
            return getattr(column["type"], "length", None)
    return None


def upgrade():
    for table in ("alert_events", "rag_query_logs"):
        if _column_length(table, "idempotency_key") == 512:
            continue
        op.alter_column(
            table,
            "idempotency_key",
            existing_type=sa.String(length=191),
            type_=sa.String(length=512),
            existing_nullable=True,
        )


def downgrade():
    for table in ("alert_events", "rag_query_logs"):
        if _column_length(table, "idempotency_key") == 191:
            continue
        op.alter_column(
            table,
            "idempotency_key",
            existing_type=sa.String(length=512),
            type_=sa.String(length=191),
            existing_nullable=True,
        )
