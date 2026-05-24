"""add chat message trust scores

Revision ID: 0024_chat_message_scores
Revises: 0023_unify_roles_to_6
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0024_chat_message_scores"
down_revision = "0023_unify_roles_to_6"
branch_labels = None
depends_on = None


TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "chat_message_scores",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("session_id", mysql.BINARY(16), nullable=False),
        sa.Column("user_id", mysql.BINARY(16), nullable=True),
        sa.Column("assistant_message_id", mysql.BINARY(16), nullable=False),
        sa.Column("score_version", sa.String(32), nullable=False, server_default="trust_v1"),
        sa.Column("trace_id", sa.String(128), nullable=True),
        sa.Column("observation_id", sa.String(128), nullable=True),
        sa.Column("trace_url", sa.String(512), nullable=True),
        sa.Column("model_key", sa.String(128), nullable=True),
        sa.Column("review_model", sa.String(128), nullable=True),
        sa.Column("rule_scores", mysql.JSON, nullable=True),
        sa.Column("llm_scores", mysql.JSON, nullable=True),
        sa.Column("combined_scores", mysql.JSON, nullable=True),
        sa.Column("trust_score", sa.Float(), nullable=True),
        sa.Column("hallucination_risk", sa.Float(), nullable=True),
        sa.Column("overconfidence", sa.Float(), nullable=True),
        sa.Column("has_citation", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="scored"),
        sa.Column("langfuse_synced_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_unique_constraint(
        "uq_chat_message_scores_version",
        "chat_message_scores",
        ["org_id", "assistant_message_id", "score_version"],
    )
    op.create_index("idx_chat_message_scores_org_created", "chat_message_scores", ["org_id", "created_at"])
    op.create_index("idx_chat_message_scores_trace", "chat_message_scores", ["org_id", "trace_id"])
    op.create_index("idx_chat_message_scores_session", "chat_message_scores", ["session_id"])
    op.create_index("idx_chat_message_scores_user", "chat_message_scores", ["user_id"])
    op.create_index("idx_chat_message_scores_message", "chat_message_scores", ["assistant_message_id"])


def downgrade() -> None:
    op.drop_index("idx_chat_message_scores_message", table_name="chat_message_scores")
    op.drop_index("idx_chat_message_scores_user", table_name="chat_message_scores")
    op.drop_index("idx_chat_message_scores_session", table_name="chat_message_scores")
    op.drop_index("idx_chat_message_scores_trace", table_name="chat_message_scores")
    op.drop_index("idx_chat_message_scores_org_created", table_name="chat_message_scores")
    op.drop_constraint("uq_chat_message_scores_version", "chat_message_scores", type_="unique")
    op.drop_table("chat_message_scores")
