"""add analytics query indexes

Revision ID: 0006_analytics_query_indexes
Revises: 0005_model_config_pricing
Create Date: 2026-03-23
"""

from alembic import op


revision = "0006_analytics_query_indexes"
down_revision = "0005_model_config_pricing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_inspection_tasks_org_created", "inspection_tasks", ["org_id", "created_at"])
    op.create_index("idx_inspection_results_org_created", "inspection_results", ["org_id", "created_at"])
    op.create_index("idx_alert_events_org_created", "alert_events", ["org_id", "created_at"])
    op.create_index("idx_stability_reports_org_created", "stability_reports", ["org_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_stability_reports_org_created", table_name="stability_reports")
    op.drop_index("idx_alert_events_org_created", table_name="alert_events")
    op.drop_index("idx_inspection_results_org_created", table_name="inspection_results")
    op.drop_index("idx_inspection_tasks_org_created", table_name="inspection_tasks")
