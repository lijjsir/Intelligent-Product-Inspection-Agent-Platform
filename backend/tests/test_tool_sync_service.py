from __future__ import annotations

from app.services.tool_sync_service import ToolSyncService


def test_collect_manifests_excludes_paper_tool_when_disabled(monkeypatch):
    monkeypatch.setattr("app.services.tool_sync_service.settings.paper_review_enabled", False)

    manifests = ToolSyncService.collect_manifests()

    assert all(item.get("tool_key") != "file.paper_format_check" for item in manifests)
