"""add result feedbacks

Revision ID: 0004_result_feedbacks
Revises: 0003_token_ledger
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0004_result_feedbacks"
down_revision = "0003_token_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "result_feedbacks",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("result_id", mysql.BINARY(16), nullable=False),
        sa.Column("actor_id", mysql.BINARY(16), nullable=False),
        sa.Column("feedback_type", sa.String(16), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        ),
        sa.UniqueConstraint("actor_id", "result_id", name="uk_actor_result"),
    )
    op.create_index("idx_result_feedbacks_org_created", "result_feedbacks", ["org_id", "created_at"])


def downgrade():
    op.drop_index("idx_result_feedbacks_org_created", table_name="result_feedbacks")
    op.drop_table("result_feedbacks")

