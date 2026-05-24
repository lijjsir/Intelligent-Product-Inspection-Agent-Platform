"""unify roles to 6 new roles

Revision ID: 0023_unify_roles_to_6
Revises: 0022_memory_governance_tables
Create Date: 2026-05-11

Mapping:
  super_admin, org_admin, platform_admin, auditor --> admin
  inspector, viewer --> user
  analyst, ai_quality --> algorithm_engineer
  agent_operator --> app_developer
  api_service --> api_service (keep as machine identity)
"""
from alembic import op

revision = "0023_unify_roles_to_6"
down_revision = "0022_memory_governance_tables"
branch_labels = None
depends_on = None

ROLE_MAP = {
    "super_admin": "admin",
    "org_admin": "admin",
    "platform_admin": "admin",
    "auditor": "admin",
    "inspector": "user",
    "viewer": "user",
    "analyst": "algorithm_engineer",
    "ai_quality": "algorithm_engineer",
    "agent_operator": "app_developer",
}


def upgrade():
    for old, new in ROLE_MAP.items():
        op.execute(
            f"UPDATE users SET role = '{new}' WHERE role = '{old}'"
        )


def downgrade():
    raise NotImplementedError(
        "Cannot downgrade role unification. Restore from backup."
    )
