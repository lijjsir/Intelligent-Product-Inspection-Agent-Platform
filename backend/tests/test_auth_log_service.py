import pytest

from app.core.exceptions import ServiceUnavailableError
from app.services.auth_log_service import AuthLogService


class MissingTableRepo:
    async def write(self, _log):
        raise Exception('(1146, "Table \'piap_main.auth_logs\' doesn\'t exist")')

    async def list_logs(self, **_kwargs):
        raise Exception('(1146, "Table \'piap_main.auth_logs\' doesn\'t exist")')


@pytest.mark.asyncio
async def test_record_login_ignores_missing_auth_logs_table(monkeypatch):
    service = AuthLogService(None)
    monkeypatch.setattr(service, "_repo", MissingTableRepo())
    monkeypatch.setattr("app.services.auth_log_service._is_auth_logs_table_missing", lambda exc: "auth_logs" in str(exc))

    log = await service.record_login(
        org_id="org-1",
        username="alice",
        request=None,
        success=True,
        user_id="u1",
    )

    assert log.org_id == "org-1"
    assert log.username == "alice"
    assert log.user_id == "u1"
    assert log.success is True


@pytest.mark.asyncio
async def test_list_logs_raises_service_unavailable_when_auth_logs_table_missing(monkeypatch):
    service = AuthLogService(None)
    monkeypatch.setattr(service, "_repo", MissingTableRepo())
    monkeypatch.setattr("app.services.auth_log_service._is_auth_logs_table_missing", lambda exc: "auth_logs" in str(exc))

    with pytest.raises(ServiceUnavailableError, match="登录日志尚未初始化"):
        await service.list_logs(org_id="org-1", page=1, size=20)
