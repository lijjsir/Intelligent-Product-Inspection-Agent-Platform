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

def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade():
    if not _has_column("model_configs", "deployment_command_template"):
        op.add_column("model_configs", sa.Column("deployment_command_template", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("model_configs", "deployment_command_template")
