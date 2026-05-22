from __future__ import annotations

from typing import Any, Callable

from agent.adapters.base import BaseAgentAdapter


class PipelineAgentAdapter(BaseAgentAdapter):
    """Adapter that routes to the full agent orchestrator pipeline.

    Stub — will be implemented when real agent pipelines are ready.
    """

    async def invoke(
        self,
        *,
        room_id: str,
        agent_def: Any,
        query: str,
        context_messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        raise NotImplementedError("PipelineAgentAdapter is not yet implemented")

    async def should_participate(
        self,
        *,
        agent_def: Any,
        messages_since_last: int,
        seconds_since_last: float,
        recent_content: str,
    ) -> bool:
        raise NotImplementedError("PipelineAgentAdapter is not yet implemented")

    async def generate_autonomous_reply(
        self,
        *,
        room_id: str,
        agent_def: Any,
        recent_messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        raise NotImplementedError("PipelineAgentAdapter is not yet implemented")
