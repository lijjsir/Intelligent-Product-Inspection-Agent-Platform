from __future__ import annotations

import pytest
from sqlalchemy.dialects import mysql

from app.repositories.task_repo import TaskRepository


class _ScalarResult:
    def scalars(self) -> "_ScalarResult":
        return self

    def all(self) -> list:
        return []


class _RecordingSession:
    def __init__(self) -> None:
        self.item_statement = None

    async def scalar(self, _statement):
        return 0

    async def execute(self, statement):
        self.item_statement = statement
        return _ScalarResult()


@pytest.mark.asyncio
async def test_list_paged_eagerly_loads_v4_product_references() -> None:
    session = _RecordingSession()
    items, total = await TaskRepository(session).list_paged(
        "11111111-1111-1111-1111-111111111111",
        {},
        page=1,
        size=20,
    )

    assert items == []
    assert total == 0
    sql = str(session.item_statement.compile(dialect=mysql.dialect()))
    assert "inspection_tasks.product_category_id" in sql
    assert "inspection_tasks.quality_product_id" in sql


@pytest.mark.asyncio
async def test_user_task_list_does_not_include_other_users_supervision_tasks():
    session = _RecordingSession()
    await TaskRepository(session).list_paged(
        "org-1", {}, page=1, size=20, owner_user_id="user-1",
    )
    where_clause = str(session.item_statement.compile(dialect=mysql.dialect())).split("WHERE", 1)[1]
    assert "inspection_tasks.created_by =" in where_clause
    assert " OR " not in where_clause
    assert "supervision" not in where_clause
