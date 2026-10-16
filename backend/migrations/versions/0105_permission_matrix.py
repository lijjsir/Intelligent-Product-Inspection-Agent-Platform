"""Persist organization role permissions and personal permission overrides."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import BINARY

revision = "0105_permission_matrix"
down_revision = "0104_chat_session_preferences"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "role_permissions",
        sa.Column("org_id", BINARY(16), primary_key=True),
        sa.Column("role", sa.String(32), primary_key=True),
        sa.Column("resources", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "user_permissions",
        sa.Column("org_id", BINARY(16), primary_key=True),
        sa.Column("user_id", BINARY(16), primary_key=True),
        sa.Column("overrides", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade():
    op.drop_table("user_permissions")
    op.drop_table("role_permissions")
