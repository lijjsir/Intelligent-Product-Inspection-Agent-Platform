from __future__ import annotations

from agent.router.contracts import Capability


SURFACE_MODE_POLICY = {
    "chat": {
        "allowed_modes": ["answer", "report"],
        "forbidden_modes": ["action"],
        "allowed_agents": ["evidence", "vision", "lab_detection", "quality_analysis", "memory_governance", "file"],
    },
    "quality_task": {
        "allowed_modes": ["action", "report", "answer"],
        "forbidden_modes": [],
        "allowed_agents": ["evidence", "vision", "lab_detection", "quality_analysis", "memory_governance", "file"],
    },
    "admin": {
        "allowed_modes": ["answer", "report", "action"],
        "forbidden_modes": [],
        "allowed_agents": ["evidence", "vision", "lab_detection", "quality_analysis", "memory_governance", "file"],
    },
    "batch": {
        "allowed_modes": ["report", "action"],
        "forbidden_modes": [],
        "allowed_agents": ["evidence", "vision", "lab_detection", "quality_analysis", "memory_governance", "file"],
    },
}


CAPABILITIES: dict[str, Capability] = {
    "evidence.arbitrate": Capability(
        key="evidence.arbitrate",
        owner_agents=["evidence"],
        handler="evidence.arbitrate",
        operation="arbitrate",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="汇总 RAG、记忆和质量知识图谱证据，输出 evidence_packet。",
    ),
    "vision.inspect": Capability(
        key="vision.inspect",
        owner_agents=["vision"],
        handler="vision.inspect",
        operation="inspect",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="high",
        description="多模态视觉检验，输出 visual_inspection_result。",
    ),
    "lab.early_risk.assess": Capability(
        key="lab.early_risk.assess",
        owner_agents=["lab_detection"],
        handler="lab.early_risk.assess",
        operation="assess",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="实验室检测早期异常和风险研判，输出 lab_detection_result。",
    ),
    "quality.final_analyze": Capability(
        key="quality.final_analyze",
        owner_agents=["quality_analysis"],
        handler="quality.final_analyze",
        operation="analyze",
        mode="answer",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="综合证据、视觉、实验室结果并生成最终聊天回答。",
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
    "quality.inspection.execute": Capability(
        key="quality.inspection.execute",
        owner_agents=["quality_analysis"],
        handler="quality.inspection.execute",
        operation="execute",
        mode="action",
        surfaces=["quality_task"],
        cost_level="high",
        description="正式质量检测执行，只允许质量检测任务页面调用。",
    ),
    "memory.governance": Capability(
        key="memory.governance",
        owner_agents=["memory_governance"],
        handler="memory.governance",
        operation="govern",
        mode="report",
        surfaces=["chat", "quality_task"],
        cost_level="medium",
        description="记忆候选、污染传播和回滚治理。",
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
