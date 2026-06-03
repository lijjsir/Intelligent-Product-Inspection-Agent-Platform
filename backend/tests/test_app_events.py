from __future__ import annotations

import pytest

from app.core import events


@pytest.mark.asyncio
async def test_seed_paper_templates_on_startup_calls_ensure_ready(monkeypatch):
    calls: list[str | None] = []

    async def fake_ensure_paper_templates_ready(*, org_id=None):
        calls.append(org_id)
        return {"template_id": "test", "files": [], "index_status": "already_indexed"}

    monkeypatch.setattr(
        "agent.tools.paper_template_storage.ensure_paper_templates_ready",
        fake_ensure_paper_templates_ready,
    )
    async def fake_resolve_org_id():
        return "org-1"

    monkeypatch.setattr(events, "resolve_paper_template_embedding_org_id", fake_resolve_org_id)

    await events.seed_paper_templates_on_startup()

    assert calls == ["org-1"]


@pytest.mark.asyncio
async def test_seed_paper_templates_on_startup_does_not_block_app(monkeypatch):
    async def fake_ensure_paper_templates_ready(*, org_id=None):
        raise RuntimeError("minio unavailable")

    monkeypatch.setattr(
        "agent.tools.paper_template_storage.ensure_paper_templates_ready",
        fake_ensure_paper_templates_ready,
    )
    async def fake_resolve_org_id():
        return None

    monkeypatch.setattr(events, "resolve_paper_template_embedding_org_id", fake_resolve_org_id)

    await events.seed_paper_templates_on_startup()


@pytest.mark.asyncio
async def test_recover_interrupted_chat_workflows_on_startup_does_not_block_app(monkeypatch):
    async def fake_recover():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "app.services.chat_service.mark_interrupted_chat_workflows_on_startup",
        fake_recover,
    )

    await events.recover_interrupted_chat_workflows_on_startup()
