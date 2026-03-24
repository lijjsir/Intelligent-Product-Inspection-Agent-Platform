"""add model configs

Revision ID: 0002_model_configs
Revises: 0001_initial_schema
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0002_model_configs"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_configs",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("org_id", mysql.BINARY(16), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_key", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("endpoint", sa.String(512), nullable=False),
        sa.Column("api_key_enc", sa.Text(), nullable=True),
        sa.Column("model_type", sa.String(32), nullable=False, server_default="chat"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("rpm_limit", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("health_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("health_message", sa.String(256), nullable=True),
    )
    op.create_index("idx_model_configs_org_active_priority", "model_configs", ["org_id", "is_active", "priority"])


def downgrade():
    op.drop_index("idx_model_configs_org_active_priority", table_name="model_configs")
    op.drop_table("model_configs")

