"""normalize_rag_query_log_inspection_sources

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-20

Backfill legacy inspection-task-derived rag_query_logs rows that were stored under
quality_judgement / llm_native_quality source_graph aliases.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE rag_query_logs
            SET
              source_graph = 'inspection_task',
              agent_name = COALESCE(NULLIF(agent_name, ''), 'inspection_task'),
              sub_route = CASE
                WHEN sub_route IS NOT NULL AND sub_route <> '' THEN sub_route
                ELSE 'inspection_execute'
              END
            WHERE (
                task_id IS NOT NULL
                OR sub_route IN ('inspection_execute', 'task_create')
              )
              AND source_graph IN ('quality_judgement', 'llm_native_quality', 'legacy_quality')
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE rag_query_logs
            SET source_graph = 'llm_native_quality'
            WHERE source_graph = 'inspection_task'
              AND (
                agent_name = 'inspection_task'
                OR agent_name IS NULL
                OR agent_name = ''
              )
            """
        )
    )
