from __future__ import annotations

import httpx
import pytest

from app.services.paper_template_index_service import PaperTemplateIndexService


@pytest.mark.asyncio
async def test_paper_template_index_service_reports_actionable_qdrant_connect_error(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            raise httpx.ConnectError("All connection attempts failed", request=None)

    monkeypatch.setattr("app.services.paper_template_index_service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("app.services.paper_template_index_service.settings.qdrant_url", "http://127.0.0.1:6333")
    monkeypatch.setattr("app.services.paper_template_index_service.settings.qdrant_docker_url", "http://qdrant:6333")

    service = PaperTemplateIndexService(object())

    with pytest.raises(RuntimeError) as exc_info:
        await service._ensure_qdrant_collection(768)

    message = str(exc_info.value)
    assert "无法连接到 Qdrant 端点 http://127.0.0.1:6333" in message
    assert "http://127.0.0.1:63330" in message
    assert "http://qdrant:6333" in message
