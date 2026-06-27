"""drop memory_dependency_edges table

IMPORTANT: This migration should ONLY be run after the Neo4j migration is verified.
Run `python scripts/migrate_memory_edges_to_neo4j.py --org-id ORG_ID --verify` first.

Revision ID: 0079_drop_memory_dependency_edges
Revises: 0078_memory_fail_fast_outbox_indexes
Create Date: 2026-06-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0079_drop_memory_dependency_edges"
down_revision = "0078_memory_fail_fast_outbox_indexes"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def upgrade() -> None:
    if _has_table("memory_dependency_edges"):
        op.drop_table("memory_dependency_edges")


def downgrade() -> None:
    if not _has_table("memory_dependency_edges"):
        op.create_table(
            "memory_dependency_edges",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("source_memory_id", sa.String(64), nullable=False),
            sa.Column("target_memory_id", sa.String(64), nullable=False),
            sa.Column("source_event_id", sa.String(64), nullable=True),
            sa.Column("target_event_id", sa.String(64), nullable=True),
            sa.Column("edge_type", sa.String(64), nullable=False),
            sa.Column("strength", mysql.DECIMAL(5, 4), nullable=True),
            sa.Column("scope_json", mysql.JSON(), nullable=True),
            sa.Column("metadata_json", mysql.JSON(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="memory dependency edges graph (deprecated, replaced by Neo4j)",
        )
        op.create_index(
            "idx_mem_edge_source",
            "memory_dependency_edges",
            ["org_id", "source_memory_id", "edge_type", "deleted_at"],
        )
        op.create_index(
            "idx_mem_edge_target",
            "memory_dependency_edges",
            ["org_id", "target_memory_id", "edge_type", "deleted_at"],
        )
        op.create_index(
            "idx_mem_edge_type",
            "memory_dependency_edges",
            ["org_id", "edge_type", "deleted_at"],
        )
