"""consolidate user roles to 5 simplified roles

Revision ID: 0012_consolidate_roles
Revises: 0011_seed_default_product_model_config
Create Date: 2025-01-15

"""
from alembic import op
import sqlalchemy as sa

revision = "0012_consolidate_roles"
down_revision = "0011_seed_default_product_model"
branch_labels = None
depends_on = None


ROLE_MIGRATION_MAP = {
    "super_admin": "admin",
    "org_admin": "admin",
    "platform_admin": "admin",
    "auditor": "admin",
    "viewer": "inspector",
    "ai_quality": "analyst",
}


def upgrade() -> None:
    for old_role, new_role in ROLE_MIGRATION_MAP.items():
        op.execute(
            sa.text("UPDATE users SET role = :new_role WHERE role = :old_role"),
        ).bindparams(new_role=new_role, old_role=old_role)


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE users SET role = 'inspector' WHERE role = 'admin'"),
    )
    op.execute(
        sa.text("UPDATE users SET role = 'inspector' WHERE role = 'analyst'"),
    )
