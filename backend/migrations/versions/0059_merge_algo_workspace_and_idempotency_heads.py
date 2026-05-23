"""drop legacy training_command_template after migration renumbering

Revision ID: 0059
Revises: 0058
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if _has_column("model_configs", "training_command_template"):
        op.drop_column("model_configs", "training_command_template")


def downgrade() -> None:
    if not _has_column("model_configs", "training_command_template"):
        op.add_column("model_configs", sa.Column("training_command_template", mysql.TEXT(), nullable=True))
