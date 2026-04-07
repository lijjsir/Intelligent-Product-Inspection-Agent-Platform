import pytest

from agent.contracts import RouteSignals
from agent.graphs.quality_root.policy import select_subgraph
from app.core.config import settings


def test_select_subgraph_prefers_legacy_for_task_keywords(monkeypatch):
    monkeypatch.setattr(settings, "agent_route_mode", "router_enabled")
    decision = select_subgraph(
        RouteSignals(
            has_task_keyword=True,
            has_file_attachments=True,
            attachment_types=["txt"],
        )
    )
    assert decision.selected_subgraph == "legacy_quality"


def test_select_subgraph_routes_non_image_files_to_native(monkeypatch):
    monkeypatch.setattr(settings, "agent_route_mode", "router_enabled")
    decision = select_subgraph(
        RouteSignals(
            has_task_keyword=False,
            has_images=False,
            has_file_attachments=True,
            attachment_types=["txt"],
        )
    )
    assert decision.selected_subgraph == "llm_native_quality"


def test_select_subgraph_routes_images_to_legacy(monkeypatch):
    monkeypatch.setattr(settings, "agent_route_mode", "router_enabled")
    decision = select_subgraph(
        RouteSignals(
            has_images=True,
            attachment_types=["image"],
        )
    )
    assert decision.selected_subgraph == "legacy_quality"
