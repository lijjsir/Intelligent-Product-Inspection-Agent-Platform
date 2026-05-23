from __future__ import annotations

import logging
from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentRouterOutput
from agent.router.manager_loop import ManagerLoop
from agent.router.route_policy import AgentRoutePolicy

logger = logging.getLogger(__name__)


class AgentManager:
    """统一入口路由，通过 ManagerLoop 调度 capability-level route plan。"""

    def __init__(self) -> None:
        self._route_policy = AgentRoutePolicy()
        self._loop = ManagerLoop()
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

    async def run(self, request: NormalizedRequest, db_session=None) -> AgentRouterOutput:
        return await self._loop.run(request, db_session=db_session)

    async def _build_model_classifier_client(self, request: NormalizedRequest):
        try:
            from agent.llm.client import LLMClient
            from agent.llm.gateway import LLMGateway
            from app.services.model_config_service import ModelConfigService
            from infra.database.session import get_session

            async with get_session() as session:
                runtime_models = await ModelConfigService(session, str(request.org_id)).list_runtime_models()
            runtime = await LLMGateway().select_runtime(runtime_models)
            if not runtime:
                return None
            return LLMClient(
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                model_id=runtime.get("model_id"),
                trace_id=str(request.workflow_run_id or request.request_id),
                task_id=str(request.session_id or request.request_id),
                org_id=str(request.org_id),
                provider=str(runtime.get("provider") or ""),
                input_price_per_million=runtime.get("input_price_per_million"),
                output_price_per_million=runtime.get("output_price_per_million"),
            )
        except Exception:
            logger.debug("model classifier client unavailable; using rule fallback", exc_info=True)
            return None
