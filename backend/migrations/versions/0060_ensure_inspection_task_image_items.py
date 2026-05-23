"""ensure inspection_tasks.image_items exists on drifted databases

Revision ID: 0060
Revises: 0059
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("inspection_tasks", "image_items"):
        op.add_column(
            "inspection_tasks",
            sa.Column("image_items", mysql.JSON(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("inspection_tasks", "image_items"):
        op.drop_column("inspection_tasks", "image_items")
