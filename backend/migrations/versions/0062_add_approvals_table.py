"""add_approvals_table

Revision ID: 0062
Revises: 0061
Create Date: 2026-05-23 22:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app.models.base import UUIDBinary

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if _has_table("approvals"):
        return
    op.create_table(
        "approvals",
        sa.Column("id", UUIDBinary(length=16), nullable=False),
        sa.Column("org_id", UUIDBinary(length=16), nullable=False),
        sa.Column("source_module", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("operation_summary", sa.String(length=512), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("payload_json", mysql.JSON(), nullable=True),
        sa.Column("requester_id", UUIDBinary(length=16), nullable=False),
        sa.Column("requester_role", sa.String(length=32), nullable=False),
        sa.Column("reviewer_id", UUIDBinary(length=16), nullable=True),
        sa.Column("review_comment", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("reviewed_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_org_id", "approvals", ["org_id"], unique=False)
    op.create_index("ix_approvals_requester_id", "approvals", ["requester_id"], unique=False)
    op.create_index("ix_approvals_reviewer_id", "approvals", ["reviewer_id"], unique=False)


def downgrade():
    op.drop_index("ix_approvals_reviewer_id", table_name="approvals")
    op.drop_index("ix_approvals_requester_id", table_name="approvals")
    op.drop_index("ix_approvals_org_id", table_name="approvals")
    op.drop_table("approvals")
