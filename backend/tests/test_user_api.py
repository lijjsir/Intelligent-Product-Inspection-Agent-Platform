from datetime import datetime

import pytest

from app.api.v1 import users as users_api
from app.schemas.user import CurrentUser, UserCreate


class FakeDbSession:
    def __init__(self):
        self.refreshed = []

    async def refresh(self, obj):
        self.refreshed.append(obj)


class FakeService:
    def __init__(self, db, org_id):
        self.db = db
        self.org_id = org_id

    async def create_user(self, username, email, password, role, actor_role):
        return type(
            "FakeUser",
            (),
            {
                "id": "user-1",
                "org_id": self.org_id,
                "username": username,
                "email": email,
                "role": role,
                "is_active": True,
                "created_at": datetime(2026, 4, 5, 10, 0, 0),
                "updated_at": datetime(2026, 4, 5, 10, 0, 0),
            },
        )()


@pytest.mark.asyncio
async def test_create_user_refreshes_entity_before_response(monkeypatch):
    db = FakeDbSession()
    monkeypatch.setattr(users_api, "UserService", FakeService)

    response = await users_api.create_user(
        payload=UserCreate(
            username="tester",
            email="tester@example.com",
            password="Passw0rd!123",
            role="user",
        ),
        current=CurrentUser(user_id="admin-1", org_id="org-1", role="admin"),
        db=db,
    )

    assert response.data.username == "tester"
    assert len(db.refreshed) == 1
