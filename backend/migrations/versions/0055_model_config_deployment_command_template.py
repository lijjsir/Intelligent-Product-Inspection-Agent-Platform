"""add deployment command template to model configs

Revision ID: 0055
Revises: 0054
Create Date: 2026-05-22 23:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("model_configs", sa.Column("deployment_command_template", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("model_configs", "deployment_command_template")
