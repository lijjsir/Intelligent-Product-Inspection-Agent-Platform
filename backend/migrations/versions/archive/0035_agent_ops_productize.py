"""agent_ops_productize

Revision ID: 0035
Revises: 0034_chat_route_obs
Create Date: 2026-05-19

Add lifecycle_status, group_key, route_enabled, supports_route_toggle, customer_visible_description
to agent_definitions. Add runtime_status, health check, error tracking fields to agent_runtime_instances.
Create agent_runtime_events table. Add blocked/blocked_reason to agent_route_logs.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0035"
down_revision: Union[str, None] = "0034_chat_route_obs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agent_definitions 新增字段 ---
    op.add_column("agent_definitions", sa.Column("lifecycle_status", sa.String(32), nullable=False, server_default="active", comment="active/partial/planned/legacy/deprecated"))
    op.add_column("agent_definitions", sa.Column("group_key", sa.String(32), nullable=False, server_default="core", comment="core/memory/planned/legacy"))
    op.add_column("agent_definitions", sa.Column("route_enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE"), comment="是否参与路由"))
    op.add_column("agent_definitions", sa.Column("supports_route_toggle", sa.Boolean(), nullable=False, server_default=sa.text("TRUE"), comment="是否允许暂停恢复路由"))
    op.add_column("agent_definitions", sa.Column("customer_visible_description", sa.Text(), nullable=True, comment="给客户看的能力说明"))

    # --- agent_runtime_instances 新增字段 ---
    op.add_column("agent_runtime_instances", sa.Column("runtime_status", sa.String(32), nullable=False, server_default="stopped", comment="running/stopped/degraded/maintenance/readonly"))
    op.add_column("agent_runtime_instances", sa.Column("last_health_check_at", mysql.DATETIME(fsp=3), nullable=True))
    op.add_column("agent_runtime_instances", sa.Column("last_error_message", sa.Text(), nullable=True))
    op.add_column("agent_runtime_instances", sa.Column("last_error_at", mysql.DATETIME(fsp=3), nullable=True))
    op.add_column("agent_runtime_instances", sa.Column("maintenance_reason", sa.Text(), nullable=True))
    op.add_column("agent_runtime_instances", sa.Column("updated_by", sa.dialects.mysql.BINARY(16), nullable=True))

    # 将现有 status 值同步到 runtime_status
    op.execute(sa.text("UPDATE agent_runtime_instances SET runtime_status = status WHERE runtime_status = 'stopped'"))

    # --- 新建 agent_runtime_events 表 ---
    op.create_table(
        "agent_runtime_events",
        sa.Column("id", sa.dialects.mysql.BINARY(16), primary_key=True),
        sa.Column("org_id", sa.dialects.mysql.BINARY(16), nullable=False, index=True),
        sa.Column("agent_id", sa.dialects.mysql.BINARY(16), nullable=False, index=True),
        sa.Column("runtime_key", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False, comment="pause_route/resume_route/start/stop/maintenance"),
        sa.Column("before_status", sa.String(32), nullable=True),
        sa.Column("after_status", sa.String(32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("operator_id", sa.dialects.mysql.BINARY(16), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    # --- agent_runtime_events 复合索引 ---
    op.create_index("idx_runtime_events_agent_time", "agent_runtime_events", ["agent_id", "created_at"])

    # --- agent_route_logs 新增字段 ---
    op.add_column("agent_route_logs", sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("FALSE"), comment="是否被运行态阻止"))
    op.add_column("agent_route_logs", sa.Column("blocked_reason", sa.Text(), nullable=True, comment="阻止原因"))


def downgrade() -> None:
    op.drop_column("agent_route_logs", "blocked_reason")
    op.drop_column("agent_route_logs", "blocked")
    op.drop_index("idx_runtime_events_agent_time", table_name="agent_runtime_events")
    op.drop_table("agent_runtime_events")
    op.drop_column("agent_runtime_instances", "updated_by")
    op.drop_column("agent_runtime_instances", "maintenance_reason")
    op.drop_column("agent_runtime_instances", "last_error_at")
    op.drop_column("agent_runtime_instances", "last_error_message")
    op.drop_column("agent_runtime_instances", "last_health_check_at")
    op.drop_column("agent_runtime_instances", "runtime_status")
    op.drop_column("agent_definitions", "customer_visible_description")
    op.drop_column("agent_definitions", "supports_route_toggle")
    op.drop_column("agent_definitions", "route_enabled")
    op.drop_column("agent_definitions", "group_key")
    op.drop_column("agent_definitions", "lifecycle_status")
