from __future__ import annotations

from agent.router.contracts import Capability


SURFACE_MODE_POLICY = {
    "chat": {
        "allowed_modes": ["answer", "report"],
        "forbidden_modes": ["action"],
        "allowed_agents": ["chat", "rag", "file", "vision", "quality_report", "data_analysis"],
    },
    "quality_task": {
        "allowed_modes": ["action", "report", "answer"],
        "forbidden_modes": [],
        "allowed_agents": ["inspection_task", "rag", "file", "vision", "quality_report", "chat"],
    },
    "admin": {
        "allowed_modes": ["answer", "report", "action"],
        "forbidden_modes": [],
        "allowed_agents": ["chat", "rag", "file", "vision", "quality_report", "data_analysis"],
    },
    "batch": {
        "allowed_modes": ["report", "action"],
        "forbidden_modes": [],
        "allowed_agents": ["inspection_task", "rag", "file", "vision", "quality_report", "data_analysis"],
    },
}


CAPABILITIES: dict[str, Capability] = {
    "chat.general": Capability(
        key="chat.general",
        agent="chat",
        operation="answer",
        mode="answer",
        surfaces=["chat"],
        cost_level="low",
        description="普通聊天和平台功能问答",
    ),
    "chat.response.compose": Capability(
        key="chat.response.compose",
        agent="chat",
        operation="compose",
        mode="answer",
        surfaces=["chat", "quality_task"],
        cost_level="low",
        description="根据 artifacts 组织最终用户可读回复",
    ),
    "rag.retrieve": Capability(
        key="rag.retrieve",
        agent="rag",
        operation="retrieve",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="从用户选择的 RAG 空间检索证据",
    ),
    "rag.ingest": Capability(
        key="rag.ingest",
        agent="rag",
        operation="ingest",
        mode="action",
        surfaces=["admin", "batch"],
        cost_level="high",
        description="把文件正式写入 RAG 空间，需要显式确认和非聊天页面入口",
    ),
    "file.summary": Capability(
        key="file.summary",
        agent="file",
        operation="summarize",
        mode="report",
        surfaces=["chat"],
        cost_level="medium",
        description="聊天页面文件总结",
    ),
    "file.qa": Capability(
        key="file.qa",
        agent="file",
        operation="qa",
        mode="report",
        surfaces=["chat"],
        cost_level="medium",
        description="基于聊天上传文件回答问题",
    ),
    "image.understanding": Capability(
        key="image.understanding",
        agent="vision",
        operation="understand",
        mode="report",
        surfaces=["chat"],
        cost_level="high",
        description="聊天页面图片理解和初步判断",
    ),
    "quality.report.query": Capability(
        key="quality.report.query",
        agent="quality_report",
        operation="query",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="查询已有质量检测报告",
    ),
    "quality.task.status": Capability(
        key="quality.task.status",
        agent="quality_report",
        operation="status",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="low",
        description="查询质量检测任务状态",
    ),
    "quality.inspection.execute": Capability(
        key="quality.inspection.execute",
        agent="inspection_task",
        operation="execute",
        mode="action",
        surfaces=["quality_task"],
        cost_level="high",
        description="正式质量检测执行，只允许质量检测任务页面调用",
    ),
    "data.analysis": Capability(
        key="data.analysis",
        agent="data_analysis",
        operation="analyze",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="预留数据分析 Agent 的只读分析能力",
    ),
    "web.search": Capability(
        key="web.search",
        agent="chat",
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
    policy = surface_policy(surface)
    if surface not in capability.surfaces:
        return False
    if capability.agent not in policy["allowed_agents"]:
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
