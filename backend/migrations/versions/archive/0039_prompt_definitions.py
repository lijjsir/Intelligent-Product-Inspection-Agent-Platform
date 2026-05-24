"""prompt_definitions + prompt_sync_events + extend prompt_versions

Revision ID: 0039
Revises: 0038
Create Date: 2026-05-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_definitions",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False, index=True),
        sa.Column("prompt_key", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("agent_key", sa.String(100), nullable=True),
        sa.Column("agent_name", sa.String(100), nullable=True),
        sa.Column("stage_key", sa.String(100), nullable=True),
        sa.Column("stage_name", sa.String(100), nullable=True),
        sa.Column("usage_location", sa.String(255), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="code"),
        sa.Column("source_file", sa.String(255), nullable=True),
        sa.Column("source_symbol", sa.String(160), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=True),
        sa.Column("end_line", sa.Integer(), nullable=True),
        sa.Column("code_default_content", sa.Text(), nullable=True),
        sa.Column("code_content_hash", sa.String(64), nullable=True),
        sa.Column("active_version_id", mysql.BINARY(16), nullable=True),
        sa.Column("sync_status", sa.String(32), nullable=False, server_default="synced"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "prompt_key", name="uk_org_prompt_key"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "prompt_sync_events",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False, index=True),
        sa.Column("prompt_definition_id", mysql.BINARY(16), nullable=False, index=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("old_hash", sa.String(64), nullable=True),
        sa.Column("new_hash", sa.String(64), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    # Extend existing prompt_versions with new columns (all nullable for backward compat)
    op.add_column("prompt_versions", sa.Column("prompt_definition_id", mysql.BINARY(16), nullable=True))
    op.add_column("prompt_versions", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("prompt_versions", sa.Column("change_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("prompt_versions", "change_summary")
    op.drop_column("prompt_versions", "content_hash")
    op.drop_column("prompt_versions", "prompt_definition_id")
    op.drop_table("prompt_sync_events")
    op.drop_table("prompt_definitions")
