from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_ops import AgentDefinition, AgentRuntimeInstance


@dataclass
class RuntimeGuardResult:
    allowed: bool
    reason: str = ""
    customer_message: str = ""

    @classmethod
    def ok(cls) -> RuntimeGuardResult:
        return cls(allowed=True)

    @classmethod
    def blocked(cls, reason: str, customer_message: str) -> RuntimeGuardResult:
        return cls(allowed=False, reason=reason, customer_message=customer_message)


class AgentRuntimeGuard:
    """在执行前检查 Agent 运行时状态，确保暂停/停止操作真实生效。"""

    @staticmethod
    async def check(
        org_id: str,
        selected_agent: str,  # "chat" | "inspection_task"
        sub_route: str,
        session: AsyncSession,
    ) -> RuntimeGuardResult:
        subgraph_key = _agent_to_subgraph_key(selected_agent, sub_route)
        if not subgraph_key:
            return RuntimeGuardResult.ok()

        # 查询 Agent 定义
        def_result = await session.execute(
            select(AgentDefinition).where(
                AgentDefinition.org_id == org_id,
                AgentDefinition.subgraph_key == subgraph_key,
                AgentDefinition.deleted_at.is_(None),
            ).order_by(AgentDefinition.updated_at.desc()).limit(1)
        )
        agent_def = def_result.scalar_one_or_none()

        if not agent_def:
            return RuntimeGuardResult.blocked(
                reason=f"Agent subgraph '{subgraph_key}' not found in definitions",
                customer_message=f"服务暂不可用（{subgraph_key}），请联系管理员。",
            )

        if not agent_def.route_enabled:
            return RuntimeGuardResult.blocked(
                reason=f"Agent '{agent_def.name}' route_enabled=False",
                customer_message=f"{agent_def.name} 当前已暂停路由，请稍后重试或联系管理员恢复。",
            )

        # 查询运行时实例
        rt_result = await session.execute(
            select(AgentRuntimeInstance).where(
                AgentRuntimeInstance.org_id == org_id,
                AgentRuntimeInstance.agent_id == agent_def.id,
                AgentRuntimeInstance.deleted_at.is_(None),
            ).order_by(AgentRuntimeInstance.updated_at.desc()).limit(1)
        )
        runtime = rt_result.scalar_one_or_none()

        if runtime and runtime.runtime_status not in ("running", "degraded"):
            status_msg = {
                "stopped": "已停止运行",
                "maintenance": "正在维护中",
                "readonly": "当前为只读模式",
            }.get(runtime.runtime_status, "不可用")
            return RuntimeGuardResult.blocked(
                reason=f"Agent '{agent_def.name}' runtime_status={runtime.runtime_status}",
                customer_message=f"{agent_def.name} {status_msg}，暂时无法处理请求。",
            )

        return RuntimeGuardResult.ok()


def _agent_to_subgraph_key(selected_agent: str, sub_route: str) -> str | None:
    """将路由决策中的 agent+sub_route 映射到 subgraph_key"""
    if selected_agent == "chat":
        return "chat"
    if selected_agent == "inspection_task":
        return "inspection_task"
    # 兜底：尝试从 sub_route 推断
    if sub_route in ("general_chat", "rag_qa"):
        return "chat"
    if sub_route in ("quality_qa", "task_create", "inspection_execute"):
        return "inspection_task"
    return None
