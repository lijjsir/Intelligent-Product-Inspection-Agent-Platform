"""meeting data domain policy audit fields

Revision ID: 0081_meeting_data_domain_policy
Revises: 0080_meeting_agent_conflict_governance
Create Date: 2026-06-25 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0081_meeting_data_domain_policy"
down_revision = "0080_meeting_agent_conflict_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meeting_agent_query_audits", sa.Column("redaction_level", sa.String(length=32), nullable=True))
    op.add_column("meeting_agent_query_audits", sa.Column("denied_reasons", mysql.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("meeting_agent_query_audits", "denied_reasons")
    op.drop_column("meeting_agent_query_audits", "redaction_level")
