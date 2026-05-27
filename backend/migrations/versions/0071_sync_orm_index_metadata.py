"""sync ORM index metadata

Revision ID: 0071
Revises: 0070
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _create_index(table_name: str, index_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index(table_name: str, index_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade():
    _create_index("meeting_agent_definitions", "idx_mad_org_active", ["org_id", "is_active"])

    _drop_index("meeting_messages", "idx_meeting_messages_agent")
    _create_index("meeting_messages", "ix_meeting_messages_agent_id", ["agent_id"])

    _create_index("meeting_room_agents", "ix_meeting_room_agents_added_by", ["added_by"])
    _create_index("meeting_room_agents", "ix_meeting_room_agents_agent_id", ["agent_id"])
    _create_index("meeting_room_agents", "ix_meeting_room_agents_org_id", ["org_id"])
    _create_index("meeting_room_agents", "ix_meeting_room_agents_room_id", ["room_id"])

    _drop_index("result_feedbacks", "ix_result_feedbacks_severity")
    _drop_index("result_feedbacks", "ix_result_feedbacks_status")


def downgrade():
    _create_index("result_feedbacks", "ix_result_feedbacks_status", ["status"])
    _create_index("result_feedbacks", "ix_result_feedbacks_severity", ["severity"])

    _drop_index("meeting_room_agents", "ix_meeting_room_agents_room_id")
    _drop_index("meeting_room_agents", "ix_meeting_room_agents_org_id")
    _drop_index("meeting_room_agents", "ix_meeting_room_agents_agent_id")
    _drop_index("meeting_room_agents", "ix_meeting_room_agents_added_by")

    _drop_index("meeting_messages", "ix_meeting_messages_agent_id")
    _create_index("meeting_messages", "idx_meeting_messages_agent", ["agent_id"])

    _drop_index("meeting_agent_definitions", "idx_mad_org_active")
