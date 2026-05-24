from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.dialects import mysql

import app.api.v1.feedbacks as feedbacks_mod
from app.repositories.feedback_repo import FeedbackRepository


@dataclass
class FakeCurrentUser:
    user_id: str = "019e53f1-1927-762b-a0ff-53350cd9bb3a"
    org_id: str = "019e53f1-193f-7e83-85ea-944fc11871fc"
    role: str = "user"


class FakeFeedbackService:
    def __init__(self, db, org_id: str):
        self._db = db
        self._org_id = org_id

    async def get_detail(self, feedback_id: str):
        raise AssertionError(f"messages route was handled as feedback detail: {feedback_id}")

    async def list_message_feedbacks(self, *, target_type: str, actor_id: str, target_ids: list[str] | None = None):
        assert target_type == "chat"
        assert actor_id == FakeCurrentUser.user_id
        assert target_ids == [
            "019e53f1-1927-762b-a0ff-53350cd9bb3a",
            "019e53f1-193f-7e83-85ea-944fc11871fc",
        ]
        return []


def _build_client(monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(feedbacks_mod.router, prefix="/api/v1/feedbacks")
    app.dependency_overrides[feedbacks_mod.get_current_user] = lambda: FakeCurrentUser()

    async def _fake_db():
        yield None

    app.dependency_overrides[feedbacks_mod.get_db] = _fake_db
    monkeypatch.setattr(feedbacks_mod, "FeedbackService", FakeFeedbackService)
    return TestClient(app, raise_server_exceptions=False)


def test_list_message_feedbacks_route_is_not_shadowed_by_feedback_detail(monkeypatch):
    client = _build_client(monkeypatch)

    response = client.get(
        "/api/v1/feedbacks/messages",
        params={
            "target_type": "chat",
            "target_ids": (
                "019e53f1-1927-762b-a0ff-53350cd9bb3a,"
                "019e53f1-193f-7e83-85ea-944fc11871fc"
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


class FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class CapturingSession:
    def __init__(self):
        self.sql: list[str] = []

    async def execute(self, statement):
        compiled = str(statement.compile(dialect=mysql.dialect()))
        self.sql.append(compiled)
        return FakeScalarResult(None)


@pytest.mark.asyncio
async def test_feedback_summary_compiles_mysql_timestampdiff_interval_literal():
    session = CapturingSession()
    repo = FeedbackRepository(session)  # type: ignore[arg-type]

    await repo.summary("019e53f1-1927-762b-a0ff-53350cd9bb3a")

    avg_queries = [sql for sql in session.sql if "timestampdiff" in sql.lower()]
    assert len(avg_queries) == 1
    assert "timestampdiff(hour," in avg_queries[0].lower()
    assert "text(" not in avg_queries[0].lower()
