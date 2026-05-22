"""add_soft_delete_to_stability_and_alerts

Revision ID: 0049
Revises: 0048
Create Date: 2026-05-22 14:30:00.000000

Add deleted_at column to stability_reports and alert_events for soft-delete support.
"""

from alembic import op
import sqlalchemy as sa

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "stability_reports",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "alert_events",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column("stability_reports", "deleted_at")
    op.drop_column("alert_events", "deleted_at")
