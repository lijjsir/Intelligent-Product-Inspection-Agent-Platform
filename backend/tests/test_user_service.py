import pytest

from app.core.exceptions import ConflictError, ForbiddenError
from app.services import user_service as user_mod


class FakeSession:
    async def flush(self):
        return None

    async def refresh(self, obj):
        return None


class FakeUser:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeUserRepo:
    def __init__(self, _session):
        self.by_id = {}
        self.by_username = {}
        self.by_email = {}
        self.last_list_args = None
        self.last_count_args = None

    async def get_by_username(self, org_id, username):
        return self.by_username.get((org_id, username))

    async def get_by_email(self, org_id, email):
        return self.by_email.get((org_id, email))

    async def get_by_id(self, org_id, user_id):
        return self.by_id.get((org_id, user_id))

    async def list(self, org_id, offset, limit, keyword=None, role=None, is_active=None):
        self.last_list_args = (org_id, offset, limit, keyword, role, is_active)
        return []

    async def count(self, org_id, keyword=None, role=None, is_active=None):
        self.last_count_args = (org_id, keyword, role, is_active)
        return 0

    async def create(self, user):
        self.by_id[(user.org_id, user.id)] = user
        self.by_username[(user.org_id, user.username)] = user
        self.by_email[(user.org_id, user.email)] = user
        return user


@pytest.mark.asyncio
async def test_list_users_forwards_filters(monkeypatch):
    fake_repo = FakeUserRepo(None)
    monkeypatch.setattr(user_mod, "UserRepository", lambda session: fake_repo)

    svc = user_mod.UserService(FakeSession(), "org-1")
    await svc.list_users(2, 10, keyword="alice", role="user", is_active=True)

    assert fake_repo.last_list_args == ("org-1", 10, 10, "alice", "user", True)
    assert fake_repo.last_count_args == ("org-1", "alice", "user", True)


@pytest.mark.asyncio
async def test_update_role_rejects_self_change(monkeypatch):
    fake_repo = FakeUserRepo(None)
    monkeypatch.setattr(user_mod, "UserRepository", lambda session: fake_repo)

    svc = user_mod.UserService(FakeSession(), "org-1")
    with pytest.raises(ForbiddenError):
        await svc.update_role("user-1", "user", "admin", "user-1")


@pytest.mark.asyncio
async def test_update_profile_rejects_duplicate_email(monkeypatch):
    fake_repo = FakeUserRepo(None)
    current = FakeUser(id="user-1", org_id="org-1", username="alice", email="alice@example.com", password_hash="hashed")
    existing = FakeUser(id="user-2", org_id="org-1", username="bob", email="bob@example.com", password_hash="hashed")
    fake_repo.by_id[("org-1", "user-1")] = current
    fake_repo.by_email[("org-1", "bob@example.com")] = existing
    monkeypatch.setattr(user_mod, "UserRepository", lambda session: fake_repo)

    svc = user_mod.UserService(FakeSession(), "org-1")
    with pytest.raises(ConflictError):
        await svc.update_profile("user-1", email="bob@example.com")


@pytest.mark.asyncio
async def test_update_profile_changes_password(monkeypatch):
    fake_repo = FakeUserRepo(None)
    current = FakeUser(id="user-1", org_id="org-1", username="alice", email="alice@example.com", password_hash="hashed")
    fake_repo.by_id[("org-1", "user-1")] = current
    monkeypatch.setattr(user_mod, "UserRepository", lambda session: fake_repo)
    monkeypatch.setattr(user_mod, "verify_password", lambda raw, hashed: raw == "old-password" and hashed == "hashed")
    monkeypatch.setattr(user_mod, "hash_password", lambda raw: f"new::{raw}")

    svc = user_mod.UserService(FakeSession(), "org-1")
    user = await svc.update_profile(
        "user-1",
        username="alice-updated",
        current_password="old-password",
        new_password="new-password",
    )

    assert user.username == "alice-updated"
    assert user.password_hash == "new::new-password"


def test_get_assignable_roles_for_admin():
    roles = user_mod.UserService.get_assignable_roles("admin")
    assert roles == ["admin", "app_developer", "platform_operator", "algorithm_engineer", "user", "expert"]
