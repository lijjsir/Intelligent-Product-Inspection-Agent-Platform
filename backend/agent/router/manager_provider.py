from __future__ import annotations

import asyncio
from weakref import WeakKeyDictionary

from agent.router.agent_manager import AgentManager


_MANAGERS_BY_LOOP: WeakKeyDictionary[asyncio.AbstractEventLoop, AgentManager] = WeakKeyDictionary()


def get_agent_manager() -> AgentManager:
    """Return an AgentManager scoped to the current asyncio event loop.

    AgentManager owns async services that may lazily create loop-bound clients
    such as redis.asyncio.Redis. Celery tasks run with asyncio.run(), which
    creates and closes a fresh loop for each invocation, so a process-global
    singleton can retain clients tied to a closed loop and fail the next task
    with "Event loop is closed".
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return AgentManager()

    manager = _MANAGERS_BY_LOOP.get(loop)
    if manager is None:
        manager = AgentManager()
        _MANAGERS_BY_LOOP[loop] = manager
    return manager


def clear_agent_manager_cache() -> None:
    _MANAGERS_BY_LOOP.clear()
