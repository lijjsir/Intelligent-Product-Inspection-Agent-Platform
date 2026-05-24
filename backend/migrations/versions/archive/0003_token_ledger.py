"""add token usage ledger

Revision ID: 0003_token_ledger
Revises: 0002_model_configs
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0003_token_ledger"
down_revision = "0002_model_configs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "token_usage_ledger",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("task_id", mysql.BINARY(16), nullable=True),
        sa.Column("result_id", mysql.BINARY(16), nullable=True),
        sa.Column("model_config_id", mysql.BINARY(16), nullable=True),
        sa.Column("model_key", sa.String(128), nullable=False),
        sa.Column("product_line", sa.String(64), nullable=True),
        sa.Column("trace_id", sa.String(128), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_amount", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
    )
    op.create_index("idx_token_ledger_org_created", "token_usage_ledger", ["org_id", "created_at"])


def downgrade():
    op.drop_index("idx_token_ledger_org_created", table_name="token_usage_ledger")
    op.drop_table("token_usage_ledger")

