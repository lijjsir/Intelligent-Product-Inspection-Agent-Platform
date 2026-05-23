"""add chat agent idempotency keys

Revision ID: 0058
Revises: 0057
Create Date: 2026-05-23 03:10:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return index_name in {i["name"] for i in inspector.get_indexes(table_name)}


def upgrade():
    if not _has_column("token_usage_ledger", "idempotency_key"):
        op.add_column("token_usage_ledger", sa.Column("idempotency_key", sa.String(length=191), nullable=True))
    if not _has_index("token_usage_ledger", "uq_token_usage_ledger_idempotency_key"):
        op.create_index("uq_token_usage_ledger_idempotency_key", "token_usage_ledger", ["idempotency_key"], unique=True)
    if not _has_column("alert_events", "idempotency_key"):
        op.add_column("alert_events", sa.Column("idempotency_key", sa.String(length=191), nullable=True))
    if not _has_index("alert_events", "uq_alert_events_idempotency_key"):
        op.create_index("uq_alert_events_idempotency_key", "alert_events", ["idempotency_key"], unique=True)
    if not _has_column("rag_query_logs", "idempotency_key"):
        op.add_column("rag_query_logs", sa.Column("idempotency_key", sa.String(length=191), nullable=True))
    if not _has_index("rag_query_logs", "uq_rag_query_logs_idempotency_key"):
        op.create_index("uq_rag_query_logs_idempotency_key", "rag_query_logs", ["idempotency_key"], unique=True)


def downgrade():
    op.drop_index("uq_rag_query_logs_idempotency_key", table_name="rag_query_logs")
    op.drop_column("rag_query_logs", "idempotency_key")
    op.drop_index("uq_alert_events_idempotency_key", table_name="alert_events")
    op.drop_column("alert_events", "idempotency_key")
    op.drop_index("uq_token_usage_ledger_idempotency_key", table_name="token_usage_ledger")
    op.drop_column("token_usage_ledger", "idempotency_key")
