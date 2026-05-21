from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRouteDecision(BaseModel):
    """AgentManager 路由决策结果"""
    selected_agent: Literal["chat", "inspection_task"] = "chat"
    sub_route: Literal[
        "general_chat",
        "rag_qa",
        "quality_qa",
        "task_create",
        "inspection_execute",
    ] = "general_chat"
    intent: str = "general_chat"
    confidence: float = 1.0
    reason: str = ""
    requires_confirmation: bool = False
    route_source: Literal["manual", "rule", "model", "fallback"] = "rule"
    fallback_agent: str | None = None


class AgentRouterInput(BaseModel):
    """AgentManager 路由输入 — 从 NormalizedRequest 提取关键信号"""
    query: str = ""
    request_kind: str = "chat"
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    route_hints: dict[str, Any] = Field(default_factory=dict)
    ext: dict[str, Any] = Field(default_factory=dict)


class AgentRouterOutput(BaseModel):
    """AgentManager 输出，包装原始 Agent 输出 + 路由元信息"""
    route_decision: AgentRouteDecision
    agent_output: dict[str, Any] = Field(default_factory=dict)
    status: Literal["completed", "failed", "degraded", "blocked"] = "completed"
    degrade_reason: str | None = None
