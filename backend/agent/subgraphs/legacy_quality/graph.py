from __future__ import annotations

from agent.contracts import AgentOutput, NormalizedRequest
from agent.subgraphs.quality_chat import QualityChatGraph


class LegacyQualitySubgraph:
    def __init__(self) -> None:
        self._chat_graph = QualityChatGraph()

    async def run(self, request: NormalizedRequest) -> AgentOutput:
        if request.request_kind == "chat":
            state = await self._chat_graph.run(
                {
                    "schema_version": "1.0.0",
                    "request_id": request.request_id,
                    "workflow_run_id": request.workflow_run_id or request.request_id,
                    "session_id": request.session_id or request.request_id,
                    "assistant_message_id": request.assistant_message_id or "",
                    "org_id": request.org_id,
                    "user_id": request.user_id or "",
                    "plan_tier": request.plan_tier,
                    "capabilities": list(request.capabilities),
                    "workspace": request.workspace,
                    "query": request.query,
                    "metadata": dict(request.metadata),
                    "ext": dict(request.ext),
                    "emit": request.ext.get("emit"),
                }
            )
            payload = dict(state.get("response_payload") or {})
            return AgentOutput(
                message_type=str(payload.get("message_type") or "assistant_text"),
                answer=str(payload.get("answer") or ""),
                summary=str(payload.get("summary") or ""),
                citations=list(payload.get("citations") or []),
                quality=dict(payload.get("quality") or {}),
                action_state=str(payload.get("action_state") or "") or None,
                task_draft=dict(payload.get("task_draft") or {}) or None,
                created_task=dict(payload.get("created_task") or {}) or None,
                raw_state=state,
            )
        return AgentOutput(
            message_type="task_result",
            answer="Legacy task execution continues through the existing inspection pipeline.",
            summary="Legacy task flow selected",
        )
