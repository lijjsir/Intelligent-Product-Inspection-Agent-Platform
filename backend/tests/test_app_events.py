from __future__ import annotations

import pytest

from app.core import events


@pytest.mark.asyncio
async def test_seed_paper_templates_on_startup_calls_builtin_seed(monkeypatch):
    calls: list[bool] = []

    def fake_seed_builtin_paper_templates():
        calls.append(True)
        return {"files": []}

    monkeypatch.setattr(
        "agent.tools.paper_template_storage.seed_builtin_paper_templates",
        fake_seed_builtin_paper_templates,
    )

    await events.seed_paper_templates_on_startup()

    assert calls == [True]


@pytest.mark.asyncio
async def test_seed_paper_templates_on_startup_does_not_block_app(monkeypatch):
    def fake_seed_builtin_paper_templates():
        raise RuntimeError("minio unavailable")

    monkeypatch.setattr(
        "agent.tools.paper_template_storage.seed_builtin_paper_templates",
        fake_seed_builtin_paper_templates,
    )

    await events.seed_paper_templates_on_startup()
