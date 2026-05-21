"""normalize_rag_query_log_sources

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-20

Normalize rag_query_logs source_graph defaults and backfill legacy chat-derived rows
that were previously written as quality_judgement/llm_native_quality.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "rag_query_logs",
        "source_graph",
        existing_type=sa.String(length=64),
        server_default="unknown",
        existing_nullable=False,
    )

    op.execute(
        sa.text(
            """
            UPDATE rag_query_logs
            SET
              source_graph = 'chat',
              agent_name = COALESCE(NULLIF(agent_name, ''), 'chat'),
              sub_route = CASE
                WHEN sub_route IS NOT NULL AND sub_route <> '' THEN sub_route
                WHEN JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.intent')) = 'general_qa' THEN 'general_chat'
                WHEN JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.intent')) IN ('general_chat', 'rag_qa', 'quality_qa')
                  THEN JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.intent'))
                ELSE 'general_chat'
              END
            WHERE task_id IS NULL
              AND session_id IS NOT NULL
              AND source_graph IN ('quality_judgement', 'llm_native_quality', 'legacy_quality')
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE rag_query_logs
            SET source_graph = 'quality_judgement'
            WHERE source_graph = 'chat'
              AND task_id IS NULL
              AND session_id IS NOT NULL
              AND (
                agent_name = 'chat'
                OR agent_name IS NULL
                OR agent_name = ''
              )
            """
        )
    )
    op.alter_column(
        "rag_query_logs",
        "source_graph",
        existing_type=sa.String(length=64),
        server_default="quality_judgement",
        existing_nullable=False,
    )
