"""restore chat_messages compound indexes

Revision ID: 0072
Revises: 0071
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0072"
down_revision = "0071"
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
    _create_index("chat_messages", "idx_chat_messages_session_seq", ["session_id", "seq_no"])
    _create_index("chat_messages", "idx_chat_messages_org_session_seq", ["org_id", "session_id", "seq_no"])


def downgrade():
    _drop_index("chat_messages", "idx_chat_messages_org_session_seq")
    _drop_index("chat_messages", "idx_chat_messages_session_seq")
