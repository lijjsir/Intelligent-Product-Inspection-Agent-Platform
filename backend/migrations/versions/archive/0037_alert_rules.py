"""create alert rules

Revision ID: 0037_alert_rules
Revises: 0036_message_feedbacks
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0037_alert_rules"
down_revision = "0036_message_feedbacks"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("condition_config", mysql.JSON(), nullable=True),
        sa.Column("notification_channels", mysql.JSON(), nullable=True),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_alert_rules_org_id", "alert_rules", ["org_id"])
    op.create_index("ix_alert_rules_alert_type", "alert_rules", ["alert_type"])
    op.create_index("ix_alert_rules_enabled", "alert_rules", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_alert_rules_enabled", table_name="alert_rules")
    op.drop_index("ix_alert_rules_alert_type", table_name="alert_rules")
    op.drop_index("ix_alert_rules_org_id", table_name="alert_rules")
    op.drop_table("alert_rules")
