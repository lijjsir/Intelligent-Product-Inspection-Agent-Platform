"""unify inspection spec image count

Revision ID: 0088_unify_inspection_spec_image_count
Revises: 0087_repair_chat_session_memory_schema_drift
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0088_unify_inspection_spec_image_count"
down_revision = "0087_repair_chat_session_memory_schema_drift"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("inspection_specs"):
        return
    op.execute("UPDATE inspection_specs SET required_image_count = 1 WHERE required_image_count <> 1")


def downgrade() -> None:
    pass
