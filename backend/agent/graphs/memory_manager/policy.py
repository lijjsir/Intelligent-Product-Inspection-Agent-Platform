from __future__ import annotations

from agent.contracts import RouteDecision, RouteSignals
from app.core.config import settings


def select_subgraph(signals: RouteSignals) -> RouteDecision:
    mode = str(settings.agent_route_mode or "router_enabled").strip() or "router_enabled"
    selected = "quality_judgement"
    reason = "Default quality judgement path"
    normalized_mode = mode if mode in {"legacy_only", "canary_non_pdf", "router_enabled"} else "router_enabled"

    if normalized_mode == "legacy_only":
        reason = "Legacy-only routing mode is enabled"
    elif signals.has_task_keyword:
        selected = "quality_judgement"
        reason = "Task creation intent detected; route to quality judgement task flow"
    elif signals.has_images:
        selected = "quality_judgement"
        reason = "Image attachment detected; route to quality judgement vision workflow"
    elif signals.has_file_attachments or signals.request_kind == "chat":
        selected = "quality_judgement"
        reason = "Text or non-image file detected; route to quality judgement flow"
    return RouteDecision(
        mode=normalized_mode,
        selected_subgraph=selected,
        fallback_subgraph="quality_judgement",
        reason=reason,
        signals=signals,
    )
