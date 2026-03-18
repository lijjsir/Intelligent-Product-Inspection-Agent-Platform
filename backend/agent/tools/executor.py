from agent.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    async def execute(self, tool_name: str, payload: dict) -> dict:
        tool = self._registry.get(tool_name)
        if not tool:
            raise ValueError(f"tool not found: {tool_name}")
        handler = tool.get("handler")
        if not handler:
            return {"status": "skipped"}
        return await handler(payload)
