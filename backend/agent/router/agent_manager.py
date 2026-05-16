from __future__ import annotations

import logging
from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentRouteDecision, AgentRouterInput, AgentRouterOutput
from agent.router.route_policy import AgentRoutePolicy

logger = logging.getLogger(__name__)


class AgentManager:
    """统一入口路由，将请求分发给 QualityChatAgent 或 InspectionTaskAgent。

    AgentManager 只负责路由和分发，不直接执行业务。
    具体执行由 QualityChatGraph 和 InspectionTaskGraph 各自的 .run() 方法完成。
    """

    def __init__(self) -> None:
        self._route_policy = AgentRoutePolicy()
        self._chat_agent = None
        self._task_agent = None

    @property
    def chat_agent(self):
        if self._chat_agent is None:
            from agent.subgraphs.quality_chat import QualityChatGraph
            self._chat_agent = QualityChatGraph()
        return self._chat_agent

    @property
    def task_agent(self):
        if self._task_agent is None:
            from agent.subgraphs.inspection_task import InspectionTaskGraph
            self._task_agent = InspectionTaskGraph()
        return self._task_agent

    async def run(self, request: NormalizedRequest) -> AgentRouterOutput:
        router_input = AgentRouterInput(
            query=request.query,
            request_kind=request.request_kind,
            attachments=[item.model_dump() for item in request.attachments],
            image_urls=request.image_urls,
            route_hints=request.route_hints,
            ext=request.ext,
        )

        decision = self._route_policy.decide(router_input)

        try:
            if decision.selected_agent == "inspection_task":
                agent_output = await self.task_agent.run(request, decision)
            else:
                agent_output = await self.chat_agent.run(request, decision)
        except Exception as exc:
            logger.exception("Agent execution failed: agent=%s", decision.selected_agent)
            return AgentRouterOutput(
                route_decision=decision,
                agent_output={
                    "message_type": "agent_route_failed",
                    "answer": f"Agent 执行失败：{str(exc)}",
                    "route_decision": decision.model_dump(),
                },
                status="failed",
                degrade_reason=str(exc),
            )

        return AgentRouterOutput(
            route_decision=decision,
            agent_output=agent_output if isinstance(agent_output, dict) else agent_output.model_dump(),
            status="completed",
        )
