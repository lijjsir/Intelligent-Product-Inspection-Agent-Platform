"""add user token usage summary and ledger user binding

Revision ID: 0017_user_token_usage_summary
Revises: 0016_merge_develop_heads
Create Date: 2026-04-03

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0017_user_token_usage_summary"
down_revision = "0016_merge_develop_heads"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.add_column("token_usage_ledger", sa.Column("user_id", mysql.BINARY(16), nullable=True))
    op.create_index("idx_token_ledger_user", "token_usage_ledger", ["user_id"])

    op.execute(
        """
        UPDATE token_usage_ledger ledger
        INNER JOIN inspection_tasks task ON task.id = ledger.task_id
        SET ledger.user_id = task.created_by
        WHERE ledger.user_id IS NULL
        """
    )

    op.create_table(
        "user_token_usage_summary",
        sa.Column("user_id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("total_prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_ledger_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("user_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Per-user token usage summary",
    )
    op.create_index("idx_user_token_usage_org", "user_token_usage_summary", ["org_id"])
    op.create_index("idx_user_token_usage_total", "user_token_usage_summary", ["total_tokens"])

    op.execute(
        """
        INSERT INTO user_token_usage_summary (
            user_id,
            org_id,
            total_prompt_tokens,
            total_completion_tokens,
            total_tokens,
            total_cost,
            request_count,
            last_ledger_at
        )
        SELECT
            ledger.user_id,
            ledger.org_id,
            COALESCE(SUM(ledger.prompt_tokens), 0),
            COALESCE(SUM(ledger.completion_tokens), 0),
            COALESCE(SUM(ledger.total_tokens), 0),
            COALESCE(SUM(ledger.cost_amount), 0),
            COUNT(*),
            MAX(ledger.created_at)
        FROM token_usage_ledger ledger
        WHERE ledger.user_id IS NOT NULL
        GROUP BY ledger.user_id, ledger.org_id
        """
    )


def downgrade() -> None:
    op.drop_index("idx_user_token_usage_total", table_name="user_token_usage_summary")
    op.drop_index("idx_user_token_usage_org", table_name="user_token_usage_summary")
    op.drop_table("user_token_usage_summary")
    op.drop_index("idx_token_ledger_user", table_name="token_usage_ledger")
    op.drop_column("token_usage_ledger", "user_id")
