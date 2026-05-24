from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class BaseAgentAdapter(ABC):
    """Abstract adapter for agent invocation — LLM or pipeline backed."""

    @abstractmethod
    async def invoke(
        self,
        *,
        room_id: str,
        agent_def: Any,
        query: str,
        context_messages: list[dict[str, str]],
        emit: Callable,
        runtime_model: dict[str, Any] | None = None,
    ) -> str:
        """Called when this agent is @mentioned. Returns the agent's reply text."""
        ...

    @abstractmethod
    async def should_participate(
        self,
        *,
        agent_def: Any,
        messages_since_last: int,
        seconds_since_last: float,
        recent_content: str,
    ) -> bool:
        """Return True if the agent should autonomously speak now."""
        ...

    @abstractmethod
    async def generate_autonomous_reply(
        self,
        *,
        room_id: str,
        agent_def: Any,
        recent_messages: list[dict[str, str]],
        emit: Callable,
        runtime_model: dict[str, Any] | None = None,
    ) -> str:
        """Generate a reply when autonomous participation is triggered."""
        ...
