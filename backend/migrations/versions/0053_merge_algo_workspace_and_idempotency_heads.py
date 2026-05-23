"""merge algo workspace refactor and chat agent idempotency heads and drop legacy training_command_template

Revision ID: 0053_merge_algo_workspace_and_idempotency_heads
Revises: 0052, 0051_algo_workspace_base_model_lora_refactor
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0053_merge_algo_workspace_and_idempotency_heads"
down_revision = ("0052", "0051_algo_workspace_base_model_lora_refactor")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("model_configs", "training_command_template")


def downgrade() -> None:
    op.add_column("model_configs", sa.Column("training_command_template", mysql.TEXT(), nullable=True))
