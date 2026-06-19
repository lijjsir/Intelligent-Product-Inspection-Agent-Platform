from __future__ import annotations

from agent.router.contracts import Capability


SURFACE_MODE_POLICY = {
    "chat": {
        "allowed_modes": ["answer", "report"],
        "forbidden_modes": ["action"],
        "allowed_agents": ["chat", "file"],
    },
    "quality_task": {
        "allowed_modes": ["action", "report", "answer"],
        "forbidden_modes": [],
        "allowed_agents": ["inspection_task", "chat", "file"],
    },
    "admin": {
        "allowed_modes": ["answer", "report", "action"],
        "forbidden_modes": [],
        "allowed_agents": ["chat", "file", "inspection_task"],
    },
    "batch": {
        "allowed_modes": ["report", "action"],
        "forbidden_modes": [],
        "allowed_agents": ["inspection_task", "chat", "file"],
    },
}


CAPABILITIES: dict[str, Capability] = {
    "chat.general": Capability(
        key="chat.general",
        owner_agents=["chat"],
        handler="chat.general",
        operation="answer",
        mode="answer",
        surfaces=["chat"],
        cost_level="low",
        description="普通聊天和平台功能问答 — ChatExecutor 内部能力",
    ),
    "chat.response.compose": Capability(
        key="chat.response.compose",
        owner_agents=["chat"],
        handler="chat.response.compose",
        operation="compose",
        mode="answer",
        surfaces=["chat", "quality_task"],
        cost_level="low",
        description="根据 artifacts 组织最终用户可读回复 — ChatExecutor 内部能力",
    ),
    "rag.retrieve": Capability(
        key="rag.retrieve",
        owner_agents=["chat", "file", "inspection_task"],
        handler="rag.retrieve",
        operation="retrieve",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="知识库检索能力，不是独立 Agent。可由 chat/file/inspection_task 调用",
    ),
    "rag.ingest": Capability(
        key="rag.ingest",
        owner_agents=["file"],
        handler="rag.ingest",
        operation="ingest",
        mode="action",
        surfaces=["admin", "batch"],
        cost_level="high",
        description="把文件正式写入 RAG 空间，需要显式确认和非聊天页面入口",
    ),
    "file.summary": Capability(
        key="file.summary",
        owner_agents=["file"],
        handler="file.summary",
        operation="summarize",
        mode="report",
        surfaces=["chat"],
        cost_level="medium",
        description="聊天页面文件总结 — FileExecutor 内部能力",
    ),
    "file.qa": Capability(
        key="file.qa",
        owner_agents=["file"],
        handler="file.qa",
        operation="qa",
        mode="report",
        surfaces=["chat"],
        cost_level="medium",
        description="基于聊天上传文件回答问题 — FileExecutor 内部能力",
    ),
    "file.paper_format_check": Capability(
        key="file.paper_format_check",
        owner_agents=["file"],
        handler="file.paper_format_check",
        operation="paper_format_check",
        mode="report",
        surfaces=["chat"],
        cost_level="medium",
        description="对上传论文文档执行查非和模板格式检查 — FileExecutor 内部能力",
    ),
    "image.understanding": Capability(
        key="image.understanding",
        owner_agents=["chat", "inspection_task"],
        handler="vision.understand",
        operation="understand",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="high",
        description="图片理解能力，不是独立 Agent。可由 chat/inspection_task 调用",
    ),
    "quality.report.query": Capability(
        key="quality.report.query",
        owner_agents=["chat"],
        handler="quality.report.query",
        operation="query",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="查询已有质量检测报告 — 能力，不是独立 Agent",
    ),
    "quality.task.status": Capability(
        key="quality.task.status",
        owner_agents=["chat"],
        handler="quality.task.status",
        operation="status",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="low",
        description="查询质量检测任务状态 — 能力，不是独立 Agent",
    ),
    "quality.inspection.execute": Capability(
        key="quality.inspection.execute",
        owner_agents=["inspection_task"],
        handler="quality.inspection.execute",
        operation="execute",
        mode="action",
        surfaces=["quality_task"],
        cost_level="high",
        description="正式质量检测执行，只允许质量检测任务页面调用",
    ),
    "data.analysis": Capability(
        key="data.analysis",
        owner_agents=["chat", "file", "inspection_task"],
        handler="data.analysis",
        operation="analyze",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="数据分析能力，不是独立 Agent。可由 chat/file/inspection_task 调用",
    ),
    "web.search": Capability(
        key="web.search",
        owner_agents=["chat"],
        handler="web.search",
        operation="search",
        mode="answer",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="通过 DuckDuckGo 检索互联网公开信息",
    ),
}


def surface_policy(surface: str) -> dict:
    return SURFACE_MODE_POLICY.get(surface, SURFACE_MODE_POLICY["chat"])


def capability_allowed(capability: Capability, surface: str, allowed_modes: list[str]) -> bool:
    if capability.key == "file.paper_format_check":
        from app.core.config import settings

        if not settings.paper_review_enabled:
            return False

    policy = surface_policy(surface)
    if surface not in capability.surfaces:
        return False
    # Check that at least one owner_agent is allowed for this surface
    if not any(oa in policy["allowed_agents"] for oa in capability.owner_agents):
        return False
    if capability.mode not in allowed_modes:
        return False
    if capability.mode in policy.get("forbidden_modes", []):
        return False
    return True


def capabilities_for_surface(surface: str, allowed_modes: list[str] | None = None) -> dict[str, Capability]:
    policy = surface_policy(surface)
    modes = list(allowed_modes or policy["allowed_modes"])
    return {
        key: capability
        for key, capability in CAPABILITIES.items()
        if capability_allowed(capability, surface, modes)
    }
