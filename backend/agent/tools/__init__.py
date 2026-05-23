"""Agent tools — unified tool system: ToolSpec, ToolRegistry, ToolInvoker, builtin tools."""

from agent.tools.registry import ToolRegistry

# Global registry singleton — populated by builtin/__init__.py register_all()
_global_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
        from agent.tools.builtin import register_all
        register_all(_global_registry)
    return _global_registry
