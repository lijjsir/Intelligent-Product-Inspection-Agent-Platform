"""add dataset video sample count

Revision ID: 0064
Revises: 0063
Create Date: 2026-05-24 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    if not _has_column("datasets", "video_sample_count"):
        op.add_column("datasets", sa.Column("video_sample_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    if _has_column("datasets", "video_sample_count"):
        op.drop_column("datasets", "video_sample_count")
