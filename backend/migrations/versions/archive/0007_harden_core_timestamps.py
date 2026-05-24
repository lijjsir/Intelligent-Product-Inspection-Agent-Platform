"""harden core table timestamps

Revision ID: 0007_harden_core_timestamps
Revises: 0006_analytics_query_indexes
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0007_harden_core_timestamps"
down_revision = "0006_analytics_query_indexes"
branch_labels = None
depends_on = None


TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def _repair_existing_pair(table_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET
              created_at = COALESCE(created_at, updated_at, CURRENT_TIMESTAMP(3)),
              updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP(3))
            WHERE created_at IS NULL OR updated_at IS NULL
            """
        )
    )
    op.alter_column(
        table_name,
        "created_at",
        existing_type=mysql.DATETIME(fsp=3),
        nullable=False,
        server_default=TS_DEFAULT,
    )
    op.alter_column(
        table_name,
        "updated_at",
        existing_type=mysql.DATETIME(fsp=3),
        nullable=False,
        server_default=TS_UPDATE_DEFAULT,
    )


def _repair_created_and_add_updated(table_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP(3))
            WHERE created_at IS NULL
            """
        )
    )
    op.alter_column(
        table_name,
        "created_at",
        existing_type=mysql.DATETIME(fsp=3),
        nullable=False,
        server_default=TS_DEFAULT,
    )
    op.add_column(
        table_name,
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=True, server_default=TS_UPDATE_DEFAULT),
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP(3))
            WHERE updated_at IS NULL
            """
        )
    )
    op.alter_column(
        table_name,
        "updated_at",
        existing_type=mysql.DATETIME(fsp=3),
        nullable=False,
        server_default=TS_UPDATE_DEFAULT,
    )


def _add_created_and_updated(table_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=True, server_default=TS_DEFAULT),
    )
    op.add_column(
        table_name,
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=True, server_default=TS_UPDATE_DEFAULT),
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET
              created_at = COALESCE(created_at, CURRENT_TIMESTAMP(3)),
              updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP(3))
            WHERE created_at IS NULL OR updated_at IS NULL
            """
        )
    )
    op.alter_column(
        table_name,
        "created_at",
        existing_type=mysql.DATETIME(fsp=3),
        nullable=False,
        server_default=TS_DEFAULT,
    )
    op.alter_column(
        table_name,
        "updated_at",
        existing_type=mysql.DATETIME(fsp=3),
        nullable=False,
        server_default=TS_UPDATE_DEFAULT,
    )


def upgrade() -> None:
    for table_name in [
        "organizations",
        "users",
        "inspection_tasks",
        "inspection_results",
        "result_feedbacks",
        "tool_registry",
    ]:
        _repair_existing_pair(table_name)

    for table_name in [
        "stability_reports",
        "alert_events",
        "tool_executions",
        "audit_outbox",
        "token_usage_ledger",
    ]:
        _repair_created_and_add_updated(table_name)

    _add_created_and_updated("model_configs")


def downgrade() -> None:
    for table_name in ["model_configs"]:
        op.drop_column(table_name, "updated_at")
        op.drop_column(table_name, "created_at")

    for table_name in [
        "stability_reports",
        "alert_events",
        "tool_executions",
        "audit_outbox",
        "token_usage_ledger",
    ]:
        op.drop_column(table_name, "updated_at")
        op.alter_column(
            table_name,
            "created_at",
            existing_type=mysql.DATETIME(fsp=3),
            nullable=True,
            server_default=TS_DEFAULT,
        )

    for table_name in [
        "organizations",
        "users",
        "inspection_tasks",
        "inspection_results",
        "result_feedbacks",
        "tool_registry",
    ]:
        op.alter_column(
            table_name,
            "updated_at",
            existing_type=mysql.DATETIME(fsp=3),
            nullable=True,
            server_default=TS_UPDATE_DEFAULT,
        )
        op.alter_column(
            table_name,
            "created_at",
            existing_type=mysql.DATETIME(fsp=3),
            nullable=True,
            server_default=TS_DEFAULT,
        )
