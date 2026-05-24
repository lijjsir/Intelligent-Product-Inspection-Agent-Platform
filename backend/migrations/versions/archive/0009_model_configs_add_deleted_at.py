"""add deleted_at to model configs

Revision ID: 0009_model_cfg_deleted_at
Revises: 0008_inspection_specs
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0009_model_cfg_deleted_at"
down_revision = "0008_inspection_specs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("model_configs")}
    if "deleted_at" not in columns:
        op.add_column("model_configs", sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("model_configs")}
    if "deleted_at" in columns:
        op.drop_column("model_configs", "deleted_at")
