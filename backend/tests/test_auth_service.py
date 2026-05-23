import types
import pytest

from app.services import auth_service as auth_mod
from app.services import alert_rule_service as alert_rule_mod
from app.core.exceptions import ForbiddenError, ConflictError
from app.core.permissions import ROLE_ADMIN
from app.services.auth_log_service import _is_auth_logs_table_missing


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


class FakeAuthLogService:
    def __init__(self, _session):
        self.records = []

    async def record_login(self, **payload):
        self.records.append(payload)
        return types.SimpleNamespace(**payload)


@pytest.mark.asyncio
async def test_login_success(monkeypatch):
    fake_user_repo = FakeUserRepo(None)
    fake_org_repo = FakeOrgRepo(None)
    fake_auth_log_service = FakeAuthLogService(None)
    fake_org_repo.orgs["org-1"] = FakeOrg(id="org-1", is_active=True)
    fake_user_repo.users[("org-1", "alice")] = FakeUser(
        id="u1",
        org_id="org-1",
        username="alice",
        password_hash="hashed",
        role="admin",
        is_active=True,
    )

    monkeypatch.setattr(auth_mod, "UserRepository", lambda s: fake_user_repo)
    monkeypatch.setattr(auth_mod, "OrganizationRepository", lambda s: fake_org_repo)
    monkeypatch.setattr(auth_mod, "AuthLogService", lambda s: fake_auth_log_service)
    monkeypatch.setattr(auth_mod, "verify_password", lambda p, h: True)
    monkeypatch.setattr(auth_mod, "create_access_token", lambda **_: "access")
    monkeypatch.setattr(auth_mod, "create_refresh_token", lambda **_: "refresh")

    svc = auth_mod.AuthService(None)
    _, access, refresh = await svc.login("org-1", "alice", "pw")
    assert access == "access"
    assert refresh == "refresh"
    assert fake_auth_log_service.records == [
        {
            "org_id": "org-1",
            "username": "alice",
            "request": None,
            "success": True,
            "user_id": "u1",
        }
    ]


@pytest.mark.asyncio
async def test_login_disabled_user(monkeypatch):
    fake_user_repo = FakeUserRepo(None)
    fake_org_repo = FakeOrgRepo(None)
    fake_auth_log_service = FakeAuthLogService(None)
    fake_org_repo.orgs["org-1"] = FakeOrg(id="org-1", is_active=True)
    fake_user_repo.users[("org-1", "alice")] = FakeUser(
        id="u1",
        org_id="org-1",
        username="alice",
        password_hash="hashed",
        role="admin",
        is_active=False,
    )

    monkeypatch.setattr(auth_mod, "UserRepository", lambda s: fake_user_repo)
    monkeypatch.setattr(auth_mod, "OrganizationRepository", lambda s: fake_org_repo)
    monkeypatch.setattr(auth_mod, "AuthLogService", lambda s: fake_auth_log_service)
    monkeypatch.setattr(auth_mod, "verify_password", lambda p, h: True)

    svc = auth_mod.AuthService(None)
    with pytest.raises(ForbiddenError):
        await svc.login("org-1", "alice", "pw")
    assert fake_auth_log_service.records == [
        {
            "org_id": "org-1",
            "username": "alice",
            "request": None,
            "success": False,
            "user_id": "u1",
            "detail": "user disabled",
        }
    ]


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
    seeded_org_ids = []

    async def fake_seed_default_rules(_session, org_id):
        seeded_org_ids.append(org_id)

    monkeypatch.setattr(auth_mod, "UserRepository", lambda s: fake_user_repo)
    monkeypatch.setattr(auth_mod, "OrganizationRepository", lambda s: fake_org_repo)
    monkeypatch.setattr(auth_mod, "hash_password", lambda p: "hashed")
    monkeypatch.setattr(auth_mod, "create_access_token", lambda **_: "access")
    monkeypatch.setattr(auth_mod, "create_refresh_token", lambda **_: "refresh")
    monkeypatch.setattr(
        alert_rule_mod.AlertRuleService,
        "seed_default_rules",
        staticmethod(fake_seed_default_rules),
    )

    svc = auth_mod.AuthService(None)
    user, access, refresh = await svc.register("PIAP", "piap", "admin", "a@a.com", "pw")
    assert access == "access"
    assert refresh == "refresh"
    assert user.role == ROLE_ADMIN
    assert seeded_org_ids == [user.org_id]


@pytest.mark.asyncio
async def test_login_success_ignores_missing_auth_logs_table(monkeypatch):
    fake_user_repo = FakeUserRepo(None)
    fake_org_repo = FakeOrgRepo(None)
    fake_org_repo.orgs["org-1"] = FakeOrg(id="org-1", is_active=True)
    fake_user_repo.users[("org-1", "alice")] = FakeUser(
        id="u1",
        org_id="org-1",
        username="alice",
        password_hash="hashed",
        role="admin",
        is_active=True,
    )

    class MissingTableAuthLogService:
        def __init__(self, _session):
            pass

        async def record_login(self, **_payload):
            raise Exception('(1146, "Table \'piap_main.auth_logs\' doesn\'t exist")')

    monkeypatch.setattr(auth_mod, "UserRepository", lambda s: fake_user_repo)
    monkeypatch.setattr(auth_mod, "OrganizationRepository", lambda s: fake_org_repo)
    monkeypatch.setattr(auth_mod, "AuthLogService", lambda s: MissingTableAuthLogService(s))
    monkeypatch.setattr(auth_mod, "verify_password", lambda p, h: True)
    monkeypatch.setattr(auth_mod, "create_access_token", lambda **_: "access")
    monkeypatch.setattr(auth_mod, "create_refresh_token", lambda **_: "refresh")
    monkeypatch.setattr(auth_mod, "_is_auth_logs_table_missing", lambda exc: "auth_logs" in str(exc))

    svc = auth_mod.AuthService(None)
    _, access, refresh = await svc.login("org-1", "alice", "pw")
    assert access == "access"
    assert refresh == "refresh"
