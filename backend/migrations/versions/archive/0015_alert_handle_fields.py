"""add alert handling audit fields: suppressed_by, suppressed_at, action_note

Revision ID: 0015_alert_handle_fields
Revises: 0014_agent_management_tables
Create Date: 2026-04-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0015_alert_handle_fields"
down_revision = "0014_agent_management_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_events", sa.Column("suppressed_by", mysql.BINARY(16), nullable=True))
    op.add_column("alert_events", sa.Column("suppressed_at", sa.DateTime(timezone=False), nullable=True))
    op.add_column("alert_events", sa.Column("action_note", sa.String(1024), nullable=True))


def downgrade() -> None:
    op.drop_column("alert_events", "action_note")
    op.drop_column("alert_events", "suppressed_at")
    op.drop_column("alert_events", "suppressed_by")
