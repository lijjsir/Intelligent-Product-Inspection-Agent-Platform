from __future__ import annotations

from agent.contracts import RouteDecision, RouteSignals
from app.core.config import settings


def select_subgraph(signals: RouteSignals) -> RouteDecision:
    mode = str(settings.agent_route_mode or "router_enabled").strip() or "router_enabled"
    selected_agent = "chat"
    sub_route = "general_chat"
    reason = "Default quality judgement path"
    normalized_mode = mode if mode in {"legacy_only", "canary_non_pdf", "router_enabled"} else "router_enabled"

    if normalized_mode == "legacy_only":
        reason = "Legacy-only routing mode is enabled"
    elif signals.has_images or signals.has_file_attachments:
        selected_agent = "inspection_task"
        sub_route = "inspection_execute"
        reason = "Attachment detected; route to structured inspection workflow"
    elif signals.has_task_keyword:
        selected_agent = "inspection_task"
        sub_route = "task_create"
        reason = "Task creation intent detected; route to quality task draft flow"
    elif signals.request_kind == "chat":
        selected_agent = "chat"
        sub_route = "rag_qa" if signals.needs_external_knowledge or signals.selected_rag_space_id else "general_chat"
        reason = "Text or non-image file detected; route to quality judgement flow"
    return RouteDecision(
        mode=normalized_mode,
        selected_agent=selected_agent,
        sub_route=sub_route,
        intent=sub_route,
        reason=reason,
        signals=signals,
    )
