from __future__ import annotations

from agent.contracts import RouteDecision, RouteSignals
from app.core.config import settings


def select_subgraph(signals: RouteSignals) -> RouteDecision:
    mode = str(settings.agent_route_mode or "router_enabled").strip() or "router_enabled"
    selected = "legacy_quality"
    reason = "Default legacy compatibility mode"
    normalized_mode = mode if mode in {"legacy_only", "canary_non_pdf", "router_enabled"} else "router_enabled"

    if normalized_mode == "legacy_only":
        reason = "Legacy-only routing mode is enabled"
    elif signals.has_task_keyword:
        selected = "legacy_quality"
        reason = "Task creation intent detected; route to legacy task flow"
    elif signals.has_images:
        selected = "legacy_quality"
        reason = "Image attachment detected; route to legacy vision workflow"
    elif signals.has_file_attachments or signals.request_kind == "chat":
        selected = "llm_native_quality"
        reason = "Text or non-image file detected; route to LLM-native quality flow"
    return RouteDecision(
        mode=normalized_mode,
        selected_subgraph=selected,
        fallback_subgraph="legacy_quality",
        reason=reason,
        signals=signals,
    )
