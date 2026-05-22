"""add_image_items_to_inspection_tasks

Revision ID: 0048
Revises: 0047
Create Date: 2026-05-22 14:00:00.000000

Add image_items JSON column to inspection_tasks for per-image tracking
(image index, url, content hash) and duplicate detection.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inspection_tasks",
        sa.Column("image_items", mysql.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("inspection_tasks", "image_items")
