from __future__ import annotations

from functools import lru_cache

from agent.router.agent_manager import AgentManager


@lru_cache(maxsize=1)
def get_agent_manager() -> AgentManager:
    """Process-level singleton for AgentManager. Reuses compiled graph structures."""
    return AgentManager()
