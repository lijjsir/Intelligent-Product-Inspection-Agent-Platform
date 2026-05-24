"""create memory governance tables

Revision ID: 0022_memory_governance_tables
Revises: 0021_seed_demo_snapshot
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0022_memory_governance_tables"
down_revision = "0021_seed_demo_snapshot"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    # memory_items
    op.create_table(
        "memory_items",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("memory_id", sa.String(64), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("user_id", sa.BINARY(16), nullable=True),
        sa.Column("workspace", sa.String(32), nullable=False),
        sa.Column("memory_type", sa.String(64), nullable=False),
        sa.Column("scope_json", mysql.JSON, nullable=True),
        sa.Column("content_summary", sa.Text, nullable=True),
        sa.Column("content_json", mysql.JSON, nullable=True),
        sa.Column("source_event_ids", mysql.JSON, nullable=True),
        sa.Column("evidence_pointers", mysql.JSON, nullable=True),
        sa.Column("version_parent_id", sa.String(64), nullable=True),
        sa.Column("trust_score", sa.DECIMAL(5, 4), nullable=True),
        sa.Column("confidence", sa.DECIMAL(5, 4), nullable=True),
        sa.Column("visibility_scope", mysql.JSON, nullable=True),
        sa.Column("usage_policy", sa.String(32), nullable=False, server_default="context_only"),
        sa.Column("ttl_policy", sa.String(32), nullable=False, server_default="90d"),
        sa.Column("privacy_level", sa.String(32), nullable=False, server_default="tenant_private"),
        sa.Column("status", sa.String(32), nullable=False, server_default="candidate"),
        sa.Column("rollback_policy", mysql.JSON, nullable=True),
        sa.Column("created_by", sa.BINARY(16), nullable=True),
        sa.Column("created_by_type", sa.String(32), nullable=True),
        sa.Column("trace_id", sa.String(128), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("expires_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="shared memory items fact table",
    )
    op.create_index("idx_memory_items_org_status", "memory_items", ["org_id", "status", "updated_at"])
    op.create_index("idx_memory_items_org_type", "memory_items", ["org_id", "memory_type", "workspace"])
    op.create_index("idx_memory_items_trace", "memory_items", ["org_id", "trace_id"])
    op.create_index("idx_memory_items_memory_id", "memory_items", ["org_id", "memory_id"])
    op.create_index("idx_memory_items_user", "memory_items", ["org_id", "user_id", "memory_type"])

    # memory_events
    op.create_table(
        "memory_events",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("user_id", sa.BINARY(16), nullable=True),
        sa.Column("workspace", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("source_kind", sa.String(64), nullable=True),
        sa.Column("agent_id", sa.String(128), nullable=True),
        sa.Column("role", sa.String(64), nullable=True),
        sa.Column("task_id", sa.BINARY(16), nullable=True),
        sa.Column("trace_id", sa.String(128), nullable=True),
        sa.Column("memory_id", sa.String(64), nullable=True),
        sa.Column("payload_ref", sa.Text, nullable=True),
        sa.Column("payload_json", mysql.JSON, nullable=True),
        sa.Column("risk_tags", mysql.JSON, nullable=True),
        sa.Column("parent_event_ids", mysql.JSON, nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="shared memory event log",
    )
    op.create_index("idx_memory_events_org", "memory_events", ["org_id", "created_at"])
    op.create_index("idx_memory_events_trace", "memory_events", ["org_id", "trace_id"])
    op.create_index("idx_memory_events_memory", "memory_events", ["org_id", "memory_id"])
    op.create_index("idx_memory_events_type", "memory_events", ["org_id", "event_type"])

    # memory_dependency_edges
    op.create_table(
        "memory_dependency_edges",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("source_memory_id", sa.String(64), nullable=False),
        sa.Column("target_memory_id", sa.String(64), nullable=False),
        sa.Column("source_event_id", sa.String(64), nullable=True),
        sa.Column("target_event_id", sa.String(64), nullable=True),
        sa.Column("edge_type", sa.String(64), nullable=False),
        sa.Column("strength", sa.DECIMAL(5, 4), nullable=True),
        sa.Column("scope_json", mysql.JSON, nullable=True),
        sa.Column("metadata_json", mysql.JSON, nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="explicit dependency edges between memories",
    )
    op.create_index("idx_mem_dep_edges_source", "memory_dependency_edges", ["org_id", "source_memory_id"])
    op.create_index("idx_mem_dep_edges_target", "memory_dependency_edges", ["org_id", "target_memory_id"])
    op.create_index("idx_mem_dep_edges_type", "memory_dependency_edges", ["org_id", "edge_type"])

    # memory_policies
    op.create_table(
        "memory_policies",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("workspace", sa.String(32), nullable=False),
        sa.Column("policy_key", sa.String(128), nullable=False),
        sa.Column("policy_type", sa.String(64), nullable=False),
        sa.Column("config_json", mysql.JSON, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_by", sa.BINARY(16), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="memory governance policies",
    )
    op.create_index("idx_memory_policies_key", "memory_policies", ["org_id", "policy_key", "version"])

    # memory_rollbacks
    op.create_table(
        "memory_rollbacks",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("rollback_id", sa.String(64), nullable=False),
        sa.Column("root_memory_id", sa.String(64), nullable=False),
        sa.Column("operator_id", sa.BINARY(16), nullable=False),
        sa.Column("workspace", sa.String(32), nullable=False),
        sa.Column("rollback_action", sa.String(32), nullable=False),
        sa.Column("target_memory_ids", mysql.JSON, nullable=True),
        sa.Column("propagation_graph_json", mysql.JSON, nullable=True),
        sa.Column("before_snapshot_json", mysql.JSON, nullable=True),
        sa.Column("after_snapshot_json", mysql.JSON, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("require_human_review", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("review_status", sa.String(32), nullable=False, server_default="not_required"),
        sa.Column("trace_id", sa.String(128), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="memory rollback records",
    )
    op.create_index("idx_memory_rollbacks_root", "memory_rollbacks", ["org_id", "root_memory_id"])
    op.create_index("idx_memory_rollbacks_rollback", "memory_rollbacks", ["org_id", "rollback_id"])

    # memory_evaluations
    op.create_table(
        "memory_evaluations",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("evaluation_id", sa.String(64), nullable=False),
        sa.Column("rollback_id", sa.String(64), nullable=True),
        sa.Column("task_id", sa.BINARY(16), nullable=True),
        sa.Column("trace_id", sa.String(128), nullable=True),
        sa.Column("scenario", sa.String(128), nullable=True),
        sa.Column("metrics_json", mysql.JSON, nullable=True),
        sa.Column("replay_result_json", mysql.JSON, nullable=True),
        sa.Column("conclusion", sa.Text, nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="post-rollback evaluation records",
    )
    op.create_index("idx_memory_evaluations_rollback", "memory_evaluations", ["org_id", "rollback_id"])


def downgrade() -> None:
    op.drop_index("idx_memory_evaluations_rollback", "memory_evaluations")
    op.drop_table("memory_evaluations")
    op.drop_index("idx_memory_rollbacks_rollback", "memory_rollbacks")
    op.drop_index("idx_memory_rollbacks_root", "memory_rollbacks")
    op.drop_table("memory_rollbacks")
    op.drop_index("idx_memory_policies_key", "memory_policies")
    op.drop_table("memory_policies")
    op.drop_index("idx_mem_dep_edges_type", "memory_dependency_edges")
    op.drop_index("idx_mem_dep_edges_target", "memory_dependency_edges")
    op.drop_index("idx_mem_dep_edges_source", "memory_dependency_edges")
    op.drop_table("memory_dependency_edges")
    op.drop_index("idx_memory_events_type", "memory_events")
    op.drop_index("idx_memory_events_memory", "memory_events")
    op.drop_index("idx_memory_events_trace", "memory_events")
    op.drop_index("idx_memory_events_org", "memory_events")
    op.drop_table("memory_events")
    op.drop_index("idx_memory_items_user", "memory_items")
    op.drop_index("idx_memory_items_memory_id", "memory_items")
    op.drop_index("idx_memory_items_trace", "memory_items")
    op.drop_index("idx_memory_items_org_type", "memory_items")
    op.drop_index("idx_memory_items_org_status", "memory_items")
    op.drop_table("memory_items")
