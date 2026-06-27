from __future__ import annotations

import pytest

from app.core import events


@pytest.mark.asyncio
async def test_seed_paper_templates_on_startup_calls_ensure_ready(monkeypatch):
    calls: list[bool] = []

    async def fake_ensure_paper_templates_ready():
        calls.append(True)
        return {"template_id": "test", "files": [], "index_status": "already_indexed"}

    monkeypatch.setattr(
        "agent.tools.paper_template_storage.ensure_paper_templates_ready",
        fake_ensure_paper_templates_ready,
    )

    await events.seed_paper_templates_on_startup()

    assert calls == [True]


@pytest.mark.asyncio
async def test_seed_paper_templates_on_startup_does_not_block_app(monkeypatch):
    async def fake_ensure_paper_templates_ready():
        raise RuntimeError("minio unavailable")

    monkeypatch.setattr(
        "agent.tools.paper_template_storage.ensure_paper_templates_ready",
        fake_ensure_paper_templates_ready,
    )

    await events.seed_paper_templates_on_startup()
