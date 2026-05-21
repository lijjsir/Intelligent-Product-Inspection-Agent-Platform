"""add alert_events.rule_id FK to alert_rules

Revision ID: 0038_add_alert_rule_id_fk_to_alert_events
Revises: 0037_alert_rules
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0038_alert_rule_fk"
down_revision = "0037_alert_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_events",
        sa.Column("rule_id", sa.BINARY(16), nullable=True),
    )
    op.create_index("ix_alert_events_rule_id", "alert_events", ["rule_id"])
    op.create_foreign_key(
        "fk_alert_events_rule_id",
        "alert_events",
        "alert_rules",
        ["rule_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_alert_events_rule_id", "alert_events", type_="foreignkey")
    op.drop_index("ix_alert_events_rule_id", table_name="alert_events")
    op.drop_column("alert_events", "rule_id")
