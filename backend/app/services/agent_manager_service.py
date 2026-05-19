from __future__ import annotations

import logging
from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest, NormalizedAttachment
from agent.router import AgentManager
from agent.router.contracts import AgentRouterOutput

logger = logging.getLogger(__name__)


class AgentManagerService:
    """Agent 管理服务 — 替代原有的直接调用 QualityJudgementSubgraph 方式。

    接收标准化请求 → 调用 AgentManager 路由分发 → 返回带路由信息的输出。
    """

    def __init__(self) -> None:
        self._manager = AgentManager()

    async def run_chat(self, payload: dict, db_session=None) -> AgentRouterOutput:
        request = NormalizedRequest(
            request_kind="chat",
            request_id=str(payload["request_id"]),
            workflow_run_id=str(payload.get("workflow_run_id") or payload["request_id"]),
            session_id=str(payload["session_id"]),
            assistant_message_id=str(payload["assistant_message_id"]),
            org_id=str(payload["org_id"]),
            user_id=str(payload["user_id"]),
            workspace=str(payload.get("workspace") or "app"),
            plan_tier=str(payload.get("plan_tier") or "basic"),
            capabilities=list(payload.get("capabilities") or []),
            query=str(payload.get("query") or ""),
            metadata=dict(payload.get("metadata") or {}),
            ext=dict(payload.get("ext") or {}),
            attachments=[
                NormalizedAttachment.model_validate(item)
                for item in list(payload.get("attachments") or [])
            ],
            image_urls=[
                str(item).strip()
                for item in list(payload.get("image_urls") or [])
                if str(item).strip()
            ],
            product_id=str(payload.get("product_id") or "") or None,
            spec_code=str(payload.get("spec_code") or "") or None,
            route_hints=dict(payload.get("route_hints") or {}),
        )
        return await self._manager.run(request, db_session=db_session)
