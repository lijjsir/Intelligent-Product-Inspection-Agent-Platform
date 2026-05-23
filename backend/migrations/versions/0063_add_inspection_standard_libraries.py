"""add_inspection_standard_libraries

Revision ID: 0063
Revises: 0062
Create Date: 2026-05-23 23:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app.models.base import UUIDBinary

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inspection_standard_libraries",
        sa.Column("id", UUIDBinary(length=16), nullable=False),
        sa.Column("org_id", UUIDBinary(length=16), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("product_family", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rag_space_ids", mysql.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inspection_standard_libraries_org_id", "inspection_standard_libraries", ["org_id"], unique=False)
    op.create_index("ix_inspection_standard_libraries_product_family", "inspection_standard_libraries", ["product_family"], unique=False)


def downgrade():
    op.drop_index("ix_inspection_standard_libraries_product_family", table_name="inspection_standard_libraries")
    op.drop_index("ix_inspection_standard_libraries_org_id", table_name="inspection_standard_libraries")
    op.drop_table("inspection_standard_libraries")
