import httpx
import pytest

from app.schemas.infrastructure import InfrastructureComponentStatus
from app.services.infrastructure_service import InfrastructureService


class FakeSession:
    async def execute(self, _stmt):
        return 1


@pytest.mark.asyncio
async def test_infrastructure_service_resolves_unhealthy_overall_status(monkeypatch):
    service = InfrastructureService(FakeSession())

    async def fake_mysql():
        return InfrastructureComponentStatus(name="MySQL", kind="database", status="healthy")

    async def fake_redis():
        return InfrastructureComponentStatus(name="Redis", kind="cache", status="unhealthy")

    async def fake_qdrant():
        return InfrastructureComponentStatus(name="Qdrant", kind="vector_db", status="healthy")

    async def fake_storage():
        return InfrastructureComponentStatus(name="Local Storage", kind="storage", status="degraded")

    monkeypatch.setattr(service, "_check_mysql", fake_mysql)
    monkeypatch.setattr(service, "_check_redis", fake_redis)
    monkeypatch.setattr(service, "_check_qdrant", fake_qdrant)
    monkeypatch.setattr(service, "_check_object_storage", fake_storage)

    result = await service.check_all()

    assert result.overall_status == "unhealthy"
    assert [item.name for item in result.components] == ["MySQL", "Redis", "Qdrant", "Local Storage"]


@pytest.mark.asyncio
async def test_infrastructure_service_uses_local_storage_name(monkeypatch):
    service = InfrastructureService(FakeSession())

    class FakeStorage:
        def bucket_exists(self, _bucket):
            return True

    monkeypatch.setattr("app.services.infrastructure_service.settings.object_storage_backend", "local")
    monkeypatch.setattr("app.services.infrastructure_service.settings.local_upload_dir", ".")
    monkeypatch.setattr("app.services.infrastructure_service.build_object_storage", lambda: FakeStorage())

    result = await service._check_object_storage()

    assert result.name == "Local Storage"
    assert result.kind == "storage"


@pytest.mark.asyncio
async def test_infrastructure_service_reports_actionable_qdrant_connect_error(monkeypatch):
    service = InfrastructureService(FakeSession())

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            raise httpx.ConnectError("All connection attempts failed", request=None)

    monkeypatch.setattr("app.services.infrastructure_service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("app.services.infrastructure_service.settings.qdrant_url", "http://127.0.0.1:6333")
    monkeypatch.setattr("app.services.infrastructure_service.settings.qdrant_docker_url", "http://qdrant:6333")

    result = await service._check_qdrant()

    assert result.status == "unhealthy"
    assert "http://127.0.0.1:6333" in result.detail
    assert "127.0.0.1:63330" in result.detail
