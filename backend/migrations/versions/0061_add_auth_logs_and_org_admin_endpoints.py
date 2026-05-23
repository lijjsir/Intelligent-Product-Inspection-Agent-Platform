"""add_auth_logs_and_org_admin_endpoints

Revision ID: 0061
Revises: 0060
Create Date: 2026-05-23 17:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app.models.base import UUIDBinary

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_logs",
        sa.Column("id", UUIDBinary(length=16), nullable=False),
        sa.Column("org_id", UUIDBinary(length=16), nullable=False),
        sa.Column("user_id", UUIDBinary(length=16), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("detail", sa.String(length=512), nullable=True),
        sa.Column("occurred_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_auth_logs_org_id"), "auth_logs", ["org_id"], unique=False)
    op.create_index(op.f("ix_auth_logs_user_id"), "auth_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_auth_logs_event_type"), "auth_logs", ["event_type"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_auth_logs_event_type"), table_name="auth_logs")
    op.drop_index(op.f("ix_auth_logs_user_id"), table_name="auth_logs")
    op.drop_index(op.f("ix_auth_logs_org_id"), table_name="auth_logs")
    op.drop_table("auth_logs")
