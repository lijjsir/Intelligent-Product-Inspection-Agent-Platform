"""repair meeting conflict governance schema drift

Revision ID: 0082_repair_meeting_conflict_governance_schema
Revises: 0081_meeting_data_domain_policy
Create Date: 2026-06-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0082_repair_meeting_conflict_governance_schema"
down_revision = "0081_meeting_data_domain_policy"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _add_column_if_missing(table_name: str, column_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column_name):
        op.add_column(table_name, column)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _ensure_conflict_events_table() -> None:
    if not _has_table("meeting_conflict_events"):
        op.create_table(
            "meeting_conflict_events",
            sa.Column("id", mysql.BINARY(16), nullable=False),
            sa.Column("org_id", mysql.BINARY(16), nullable=False),
            sa.Column("room_id", mysql.BINARY(16), nullable=False),
            sa.Column("conflict_type", sa.String(length=32), nullable=False),
            sa.Column("resource_key", sa.String(length=160), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("initiator_user_id", mysql.BINARY(16), nullable=False),
            sa.Column("workflow_run_id", sa.String(length=128), nullable=True),
            sa.Column("related_message_ids", mysql.JSON(), nullable=True),
            sa.Column("candidate_actions", mysql.JSON(), nullable=True),
            sa.Column("selected_action", sa.String(length=64), nullable=True),
            sa.Column("resolved_by", mysql.BINARY(16), nullable=True),
            sa.Column("resolved_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("metadata_json", mysql.JSON(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
    else:
        _add_column_if_missing("meeting_conflict_events", "org_id", sa.Column("org_id", mysql.BINARY(16), nullable=False))
        _add_column_if_missing("meeting_conflict_events", "room_id", sa.Column("room_id", mysql.BINARY(16), nullable=False))
        _add_column_if_missing("meeting_conflict_events", "conflict_type", sa.Column("conflict_type", sa.String(length=32), nullable=False, server_default="memory_publish"))
        _add_column_if_missing("meeting_conflict_events", "resource_key", sa.Column("resource_key", sa.String(length=160), nullable=False, server_default=""))
        _add_column_if_missing("meeting_conflict_events", "status", sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"))
        _add_column_if_missing("meeting_conflict_events", "initiator_user_id", sa.Column("initiator_user_id", mysql.BINARY(16), nullable=False))
        _add_column_if_missing("meeting_conflict_events", "workflow_run_id", sa.Column("workflow_run_id", sa.String(length=128), nullable=True))
        _add_column_if_missing("meeting_conflict_events", "related_message_ids", sa.Column("related_message_ids", mysql.JSON(), nullable=True))
        _add_column_if_missing("meeting_conflict_events", "candidate_actions", sa.Column("candidate_actions", mysql.JSON(), nullable=True))
        _add_column_if_missing("meeting_conflict_events", "selected_action", sa.Column("selected_action", sa.String(length=64), nullable=True))
        _add_column_if_missing("meeting_conflict_events", "resolved_by", sa.Column("resolved_by", mysql.BINARY(16), nullable=True))
        _add_column_if_missing("meeting_conflict_events", "resolved_at", sa.Column("resolved_at", mysql.DATETIME(fsp=3), nullable=True))
        _add_column_if_missing("meeting_conflict_events", "metadata_json", sa.Column("metadata_json", mysql.JSON(), nullable=True))
        _add_column_if_missing("meeting_conflict_events", "created_at", sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT))
        _add_column_if_missing("meeting_conflict_events", "updated_at", sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT))
        _add_column_if_missing("meeting_conflict_events", "deleted_at", sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True))

    _create_index_if_missing("meeting_conflict_events", "ix_meeting_conflict_events_org_id", ["org_id"])
    _create_index_if_missing("meeting_conflict_events", "ix_meeting_conflict_events_room_id", ["room_id"])
    _create_index_if_missing("meeting_conflict_events", "ix_meeting_conflict_events_initiator_user_id", ["initiator_user_id"])
    _create_index_if_missing("meeting_conflict_events", "ix_meeting_conflict_events_resolved_by", ["resolved_by"])
    _create_index_if_missing("meeting_conflict_events", "idx_meeting_conflict_events_room_status", ["org_id", "room_id", "status"])
    _create_index_if_missing("meeting_conflict_events", "idx_meeting_conflict_events_resource", ["org_id", "room_id", "resource_key", "status"])
    _create_index_if_missing("meeting_conflict_events", "idx_meeting_conflict_events_initiator", ["org_id", "initiator_user_id"])


def _ensure_agent_query_audit_columns() -> None:
    _add_column_if_missing("meeting_agent_query_audits", "response_visibility", sa.Column("response_visibility", sa.String(length=16), nullable=True))
    _add_column_if_missing("meeting_agent_query_audits", "conflict_ref_id", sa.Column("conflict_ref_id", mysql.BINARY(16), nullable=True))
    _add_column_if_missing("meeting_agent_query_audits", "redaction_level", sa.Column("redaction_level", sa.String(length=32), nullable=True))
    _add_column_if_missing("meeting_agent_query_audits", "denied_reasons", sa.Column("denied_reasons", mysql.JSON(), nullable=True))
    _create_index_if_missing("meeting_agent_query_audits", "ix_meeting_agent_query_audits_conflict_ref_id", ["conflict_ref_id"])


def upgrade() -> None:
    _ensure_conflict_events_table()
    _ensure_agent_query_audit_columns()


def downgrade() -> None:
    # This is a repair migration for databases whose Alembic version advanced
    # while part of the 0080 DDL did not apply. Leave repaired schema intact.
    pass
