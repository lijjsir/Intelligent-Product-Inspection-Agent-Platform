"""add auditable and idempotent memory share approvals

Revision ID: 0094_memory_share_approval_workflow
Revises: 0093_meeting_context_and_objects
Create Date: 2026-08-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0094_memory_share_approval_workflow"
down_revision = "0093_meeting_context_and_objects"
branch_labels = None
depends_on = None


TABLE = "memory_transfer_logs"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(name: str) -> bool:
    return any(column["name"] == name for column in _inspector().get_columns(TABLE))


def _has_index(name: str) -> bool:
    return any(index["name"] == name for index in _inspector().get_indexes(TABLE))


def _has_unique(name: str) -> bool:
    return any(item["name"] == name for item in _inspector().get_unique_constraints(TABLE))


def upgrade() -> None:
    columns = (
        sa.Column("requested_by", sa.BINARY(16), nullable=True),
        sa.Column("decided_by", sa.BINARY(16), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    for column in columns:
        if not _has_column(column.name):
            op.add_column(TABLE, column)

    op.alter_column(
        TABLE,
        "status",
        existing_type=sa.String(32),
        existing_nullable=False,
        server_default="pending_approval",
    )

    op.execute(
        "UPDATE memory_transfer_logs "
        "SET requested_by = operator_id "
        "WHERE requested_by IS NULL"
    )
    op.execute(
        "UPDATE memory_transfer_logs "
        "SET status = 'executed' "
        "WHERE status = 'confirmed'"
    )
    op.execute(
        "UPDATE memory_transfer_logs "
        "SET decided_by = operator_id, decided_at = updated_at "
        "WHERE status IN ('executed', 'rejected', 'cancelled') AND decided_by IS NULL"
    )

    if op.get_bind().dialect.name == "mysql":
        op.execute(
            "UPDATE memory_items i "
            "JOIN collab_messages m ON m.org_id = i.org_id AND i.memory_id = "
            "COALESCE(JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.memory_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory_card.memory_id'))) "
            "JOIN collab_threads t ON t.id = m.thread_id AND t.org_id = m.org_id "
            "SET i.status = 'confirmed', i.content_json = JSON_SET("
            "COALESCE(i.content_json, JSON_OBJECT()), '$.confirmed_by', m.sender_id, "
            "'$.confirmed_at', DATE_FORMAT(m.created_at, '%Y-%m-%dT%H:%i:%s'), "
            "'$.governance_status', 'confirmed', '$.published_scope', 'meeting_room', "
            "'$.source_room_id', COALESCE("
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.source_room_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.source_context.room_id')), "
            "CASE WHEN t.source_type = 'meeting_room' THEN t.source_id ELSE NULL END)) "
            "WHERE m.message_type = 'memory_card' AND m.sender_type = 'user' "
            "AND i.status = 'candidate' "
            "AND COALESCE("
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.source_room_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.source_context.room_id')), "
            "CASE WHEN t.source_type = 'meeting_room' THEN t.source_id ELSE NULL END) IS NOT NULL "
            "AND EXISTS (SELECT 1 FROM collab_message_receipts r "
            "WHERE r.message_id = m.id AND r.action_status = 'pending' AND r.deleted_at IS NULL)"
        )
        op.execute(
            "INSERT INTO memory_scope_bindings ("
            "id, org_id, memory_id, scope_type, scope_id, permission, created_by, created_at, updated_at"
            ") "
            "SELECT UNHEX(REPLACE(UUID(), '-', '')), m.org_id, "
            "COALESCE(JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.memory_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory_card.memory_id'))), "
            "'meeting_room', COALESCE("
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.source_room_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.source_context.room_id')), "
            "CASE WHEN t.source_type = 'meeting_room' THEN t.source_id ELSE NULL END), "
            "'read', UNHEX(REPLACE(m.sender_id, '-', '')), m.created_at, m.updated_at "
            "FROM collab_messages m "
            "JOIN collab_threads t ON t.id = m.thread_id AND t.org_id = m.org_id "
            "WHERE m.message_type = 'memory_card' AND m.sender_type = 'user' "
            "AND COALESCE("
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.source_room_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.source_context.room_id')), "
            "CASE WHEN t.source_type = 'meeting_room' THEN t.source_id ELSE NULL END) IS NOT NULL "
            "AND EXISTS (SELECT 1 FROM collab_message_receipts r "
            "WHERE r.message_id = m.id AND r.action_status = 'pending' AND r.deleted_at IS NULL) "
            "AND NOT EXISTS (SELECT 1 FROM memory_scope_bindings b "
            "WHERE b.org_id = m.org_id AND b.memory_id = "
            "COALESCE(JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.memory_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory_card.memory_id'))) "
            "AND b.scope_type = 'meeting_room' AND b.scope_id = COALESCE("
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.source_room_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.source_context.room_id')), "
            "CASE WHEN t.source_type = 'meeting_room' THEN t.source_id ELSE NULL END) "
            "AND b.deleted_at IS NULL)"
        )
        op.execute(
            "INSERT INTO memory_transfer_logs ("
            "id, org_id, memory_id, from_scope_type, from_scope_id, "
            "to_scope_type, to_scope_id, transfer_reason, status, operator_id, "
            "requested_by, idempotency_key, created_at, updated_at"
            ") "
            "SELECT UNHEX(REPLACE(UUID(), '-', '')), m.org_id, "
            "COALESCE(JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.memory_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory_card.memory_id'))), "
            "'meeting_room', COALESCE("
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.source_room_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.source_context.room_id')), "
            "CASE WHEN t.source_type = 'meeting_room' THEN t.source_id ELSE 'legacy' END), "
            "CASE WHEN t.target_type = 'meeting_room' THEN 'meeting_room' ELSE 'user' END, "
            "t.target_id, '旧协作记忆卡片迁移为共享审批', 'pending_approval', "
            "UNHEX(REPLACE(m.sender_id, '-', '')), UNHEX(REPLACE(m.sender_id, '-', '')), "
            "CONCAT('legacy-collab-card:', BIN_TO_UUID(m.id)), m.created_at, m.updated_at "
            "FROM collab_messages m "
            "JOIN collab_threads t ON t.id = m.thread_id AND t.org_id = m.org_id "
            "WHERE m.message_type = 'memory_card' AND m.sender_type = 'user' "
            "AND t.target_type IN ('meeting_room', 'user') "
            "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory.memory_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(m.metadata_json, '$.memory_card.memory_id'))) IS NOT NULL "
            "AND EXISTS (SELECT 1 FROM collab_message_receipts r "
            "WHERE r.message_id = m.id AND r.action_status = 'pending' AND r.deleted_at IS NULL) "
            "AND NOT EXISTS (SELECT 1 FROM memory_transfer_logs l "
            "WHERE l.org_id = m.org_id AND l.idempotency_key = "
            "CONCAT('legacy-collab-card:', BIN_TO_UUID(m.id)))"
        )
        op.execute(
            "INSERT INTO memory_transfer_logs ("
            "id, org_id, memory_id, from_scope_type, from_scope_id, "
            "to_scope_type, to_scope_id, transfer_reason, status, operator_id, "
            "requested_by, decided_by, decided_at, decision_note, idempotency_key, created_at, updated_at"
            ") "
            "SELECT UNHEX(REPLACE(UUID(), '-', '')), b.org_id, b.memory_id, 'meeting_room', "
            "COALESCE(JSON_UNQUOTE(JSON_EXTRACT(i.scope_json, '$.source_room_id')), "
            "JSON_UNQUOTE(JSON_EXTRACT(i.scope_json, '$.room_id')), 'legacy'), "
            "'org_space', b.scope_id, '迁移前已直接发布到组织空间', 'executed', "
            "b.created_by, b.created_by, b.created_by, b.created_at, '历史发布记录', "
            "CONCAT('legacy-org-binding:', BIN_TO_UUID(b.id)), b.created_at, b.updated_at "
            "FROM memory_scope_bindings b "
            "JOIN memory_items i ON i.org_id = b.org_id AND i.memory_id = b.memory_id "
            "WHERE b.scope_type = 'org_space' AND b.deleted_at IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM memory_transfer_logs l "
            "WHERE l.org_id = b.org_id AND l.idempotency_key = "
            "CONCAT('legacy-org-binding:', BIN_TO_UUID(b.id)))"
        )

    if not _has_index("idx_memory_transfer_logs_status_created"):
        op.create_index(
            "idx_memory_transfer_logs_status_created",
            TABLE,
            ["org_id", "status", "created_at"],
        )
    if not _has_index("idx_memory_transfer_logs_target_status"):
        op.create_index(
            "idx_memory_transfer_logs_target_status",
            TABLE,
            ["org_id", "to_scope_type", "to_scope_id", "status"],
        )
    if not _has_unique("uq_memory_transfer_logs_idempotency"):
        op.create_unique_constraint(
            "uq_memory_transfer_logs_idempotency",
            TABLE,
            ["org_id", "idempotency_key"],
        )


def downgrade() -> None:
    if _has_unique("uq_memory_transfer_logs_idempotency"):
        op.drop_constraint("uq_memory_transfer_logs_idempotency", TABLE, type_="unique")
    if _has_index("idx_memory_transfer_logs_target_status"):
        op.drop_index("idx_memory_transfer_logs_target_status", table_name=TABLE)
    if _has_index("idx_memory_transfer_logs_status_created"):
        op.drop_index("idx_memory_transfer_logs_status_created", table_name=TABLE)
    for name in ("idempotency_key", "decision_note", "decided_at", "decided_by", "requested_by"):
        if _has_column(name):
            op.drop_column(TABLE, name)
    op.alter_column(
        TABLE,
        "status",
        existing_type=sa.String(32),
        existing_nullable=False,
        server_default="candidate",
    )
