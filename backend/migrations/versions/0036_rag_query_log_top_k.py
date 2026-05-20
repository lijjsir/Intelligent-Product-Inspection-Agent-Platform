"""rag_query_log_top_k

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-20

Add top_k to rag_query_logs so each retrieval record keeps the effective retrieval size.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rag_query_logs",
        sa.Column("top_k", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("rag_query_logs", "top_k")
