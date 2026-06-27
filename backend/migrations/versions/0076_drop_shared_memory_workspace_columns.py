"""drop shared memory workspace columns

Revision ID: 0076_drop_shared_memory_workspace_columns
Revises: 0075_shared_memory_operational_fields
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0076_drop_shared_memory_workspace_columns"
down_revision = "0075_shared_memory_operational_fields"
branch_labels = None
depends_on = None


MEMORY_WORKSPACE_TABLES = (
    "memory_items",
    "memory_events",
    "memory_policies",
    "memory_rollbacks",
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(col["name"] == column_name for col in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_workspace_column_if_exists(table_name: str) -> None:
    if _has_column(table_name, "workspace"):
        op.drop_column(table_name, "workspace")


def _add_workspace_column_if_missing(table_name: str) -> None:
    if not _has_table(table_name) or _has_column(table_name, "workspace"):
        return
    op.add_column(
        table_name,
        sa.Column("workspace", sa.String(32), nullable=False, server_default="app"),
    )
    op.alter_column(table_name, "workspace", server_default=None)


def upgrade():
    _drop_index_if_exists("memory_items", "idx_memory_items_org_type")
    _drop_index_if_exists("memory_items", "idx_memory_items_org_workspace_status")
    for table_name in MEMORY_WORKSPACE_TABLES:
        _drop_workspace_column_if_exists(table_name)


def downgrade():
    for table_name in MEMORY_WORKSPACE_TABLES:
        _add_workspace_column_if_missing(table_name)
    if _has_table("memory_items") and not _has_index("memory_items", "idx_memory_items_org_type"):
        op.create_index("idx_memory_items_org_type", "memory_items", ["org_id", "memory_type", "workspace"])
