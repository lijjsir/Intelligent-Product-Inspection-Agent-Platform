from __future__ import annotations

from agent.router.contracts import CapabilityContext


class WebSearchHandler:
    """Web search capability handler — delegates to ChatExecutor's web search logic."""

    async def run(self, context: CapabilityContext):
        # Web search is handled internally by ChatExecutor._execute_web_search()
        # This handler exists for registry completeness — ChatExecutor handles
        # web.search as a first-class internal capability.
        from agent.router.executors.chat_executor import ChatExecutor
        chat = ChatExecutor()
        return await chat._execute_web_search(context.step, context.state)
