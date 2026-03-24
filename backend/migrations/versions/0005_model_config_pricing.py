"""add pricing fields to model configs

Revision ID: 0005_model_config_pricing
Revises: 0004_result_feedbacks
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_model_config_pricing"
down_revision = "0004_result_feedbacks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_configs", sa.Column("input_price_per_million", sa.Numeric(12, 4), nullable=True))
    op.add_column("model_configs", sa.Column("output_price_per_million", sa.Numeric(12, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("model_configs", "output_price_per_million")
    op.drop_column("model_configs", "input_price_per_million")
