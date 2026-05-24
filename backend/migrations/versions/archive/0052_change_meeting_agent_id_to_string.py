"""change meeting agent_id columns from BINARY to VARCHAR

Revision ID: 0052
Revises: 0051
Create Date: 2026-05-23 10:00:00.000000

Change meeting_room_agents.agent_id and meeting_messages.agent_id from BINARY(16) to VARCHAR(64)
to support subgraph_key-based agent identification.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("meeting_room_agents", "agent_id",
                    existing_type=sa.BINARY(16),
                    type_=sa.String(length=64),
                    existing_nullable=False)
    op.alter_column("meeting_messages", "agent_id",
                    existing_type=sa.BINARY(16),
                    type_=sa.String(length=64),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column("meeting_messages", "agent_id",
                    existing_type=sa.String(length=64),
                    type_=sa.BINARY(16),
                    existing_nullable=True)
    op.alter_column("meeting_room_agents", "agent_id",
                    existing_type=sa.String(length=64),
                    type_=sa.BINARY(16),
                    existing_nullable=False)
