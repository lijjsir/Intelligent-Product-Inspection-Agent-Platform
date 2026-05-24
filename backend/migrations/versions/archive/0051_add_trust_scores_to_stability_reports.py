"""add_trust_scores_to_stability_reports

Revision ID: 0051
Revises: 0050
Create Date: 2026-05-22 16:00:00.000000

Add hallucination_risk and overconfidence columns to stability_reports
so inspection task trust scoring can be persisted alongside stability data.
"""

from alembic import op
import sqlalchemy as sa

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "stability_reports",
        sa.Column("hallucination_risk", sa.Float(), nullable=True),
    )
    op.add_column(
        "stability_reports",
        sa.Column("overconfidence", sa.Float(), nullable=True),
    )


def downgrade():
    op.drop_column("stability_reports", "overconfidence")
    op.drop_column("stability_reports", "hallucination_risk")
