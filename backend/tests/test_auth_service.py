import types
import pytest

from app.services import auth_service as auth_mod
from app.core.exceptions import ForbiddenError, ConflictError
from app.core.permissions import ROLE_ORG_ADMIN


class FakeUser:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeOrg:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeUserRepo:
    def __init__(self, _session):
        self.users = {}

    async def get_by_username(self, org_id, username):
        return self.users.get((org_id, username))

    async def create(self, user):
        self.users[(user.org_id, user.username)] = user
        return user


class FakeOrgRepo:
    def __init__(self, _session):
        self.orgs = {}

    async def get_by_id(self, org_id):
        return self.orgs.get(org_id)

    async def get_by_slug(self, slug):
        for org in self.orgs.values():
            if org.slug == slug:
                return org
        return None

    async def create(self, org):
        self.orgs[org.id] = org
        return org


@pytest.mark.asyncio
async def test_login_success(monkeypatch):
    fake_user_repo = FakeUserRepo(None)
    fake_org_repo = FakeOrgRepo(None)
    fake_org_repo.orgs["org-1"] = FakeOrg(id="org-1", is_active=True)
    fake_user_repo.users[("org-1", "alice")] = FakeUser(
        id="u1",
        org_id="org-1",
        username="alice",
        password_hash="hashed",
        role="org_admin",
        is_active=True,
    )

    monkeypatch.setattr(auth_mod, "UserRepository", lambda s: fake_user_repo)
    monkeypatch.setattr(auth_mod, "OrganizationRepository", lambda s: fake_org_repo)
    monkeypatch.setattr(auth_mod, "verify_password", lambda p, h: True)
    monkeypatch.setattr(auth_mod, "create_access_token", lambda **_: "access")
    monkeypatch.setattr(auth_mod, "create_refresh_token", lambda **_: "refresh")

    svc = auth_mod.AuthService(None)
    access, refresh = await svc.login("org-1", "alice", "pw")
    assert access == "access"
    assert refresh == "refresh"


@pytest.mark.asyncio
async def test_login_disabled_user(monkeypatch):
    fake_user_repo = FakeUserRepo(None)
    fake_org_repo = FakeOrgRepo(None)
    fake_org_repo.orgs["org-1"] = FakeOrg(id="org-1", is_active=True)
    fake_user_repo.users[("org-1", "alice")] = FakeUser(
        id="u1",
        org_id="org-1",
        username="alice",
        password_hash="hashed",
        role="org_admin",
        is_active=False,
    )

    monkeypatch.setattr(auth_mod, "UserRepository", lambda s: fake_user_repo)
    monkeypatch.setattr(auth_mod, "OrganizationRepository", lambda s: fake_org_repo)
    monkeypatch.setattr(auth_mod, "verify_password", lambda p, h: True)

    svc = auth_mod.AuthService(None)
    with pytest.raises(ForbiddenError):
        await svc.login("org-1", "alice", "pw")


@pytest.mark.asyncio
async def test_register_conflict(monkeypatch):
    fake_user_repo = FakeUserRepo(None)
    fake_org_repo = FakeOrgRepo(None)
    fake_org_repo.orgs["org-1"] = FakeOrg(id="org-1", slug="piap", is_active=True)

    monkeypatch.setattr(auth_mod, "UserRepository", lambda s: fake_user_repo)
    monkeypatch.setattr(auth_mod, "OrganizationRepository", lambda s: fake_org_repo)

    svc = auth_mod.AuthService(None)
    with pytest.raises(ConflictError):
        await svc.register("PIAP", "piap", "admin", "a@a.com", "pw")


@pytest.mark.asyncio
async def test_register_success(monkeypatch):
    fake_user_repo = FakeUserRepo(None)
    fake_org_repo = FakeOrgRepo(None)

    monkeypatch.setattr(auth_mod, "UserRepository", lambda s: fake_user_repo)
    monkeypatch.setattr(auth_mod, "OrganizationRepository", lambda s: fake_org_repo)
    monkeypatch.setattr(auth_mod, "hash_password", lambda p: "hashed")
    monkeypatch.setattr(auth_mod, "create_access_token", lambda **_: "access")
    monkeypatch.setattr(auth_mod, "create_refresh_token", lambda **_: "refresh")

    svc = auth_mod.AuthService(None)
    user, access, refresh = await svc.register("PIAP", "piap", "admin", "a@a.com", "pw")
    assert access == "access"
    assert refresh == "refresh"
    assert user.role == ROLE_ORG_ADMIN
