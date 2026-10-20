"""MySQL-only text normalization must preserve UUID equality on other dialects."""
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects import mysql, sqlite

from app.models.meeting import MeetingRoom, MemoryTransferLog
from app.services.collab_work_item_page_service import CollabWorkItemPageService, _ScopeUUIDText
from app.services.risk_report_listing_service import uuid_text


def test_room_uuid_scope_comparison_has_explicit_mysql_charset_and_collation():
    statement=select(MeetingRoom.id).where(_ScopeUUIDText(uuid_text(MeetingRoom.id))==MemoryTransferLog.to_scope_id)
    sql=str(statement.compile(dialect=mysql.dialect()))
    assert 'USING utf8mb4) COLLATE utf8mb4_unicode_ci' in sql
    assert 'memory_transfer_logs.to_scope_id' in sql
    portable=str(statement.compile(dialect=sqlite.dialect()))
    assert 'CONVERT(' not in portable and 'COLLATE utf8mb4' not in portable


def test_mixed_work_index_keeps_org_membership_and_host_conditions():
    service=SimpleNamespace(_session=None,_org_id=str(uuid4()),_user_id=str(uuid4()),_role='expert')
    query=select(CollabWorkItemPageService(service).index())
    sql=str(query.compile(dialect=mysql.dialect()))
    assert 'UNION ALL' in sql and 'COLLATE utf8mb4_unicode_ci' in sql
    assert 'collab_thread_participants' in sql and 'meeting_room_members' in sql
    assert 'meeting_rooms.org_id' in sql and 'memory_transfer_logs.org_id' in sql
