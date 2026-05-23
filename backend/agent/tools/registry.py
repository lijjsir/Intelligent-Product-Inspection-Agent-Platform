"""ToolRegistry — in-memory tool registration with agent/surface/mode filtering."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.tools.contracts import ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(self, spec: ToolSpec, handler: Callable[..., Any]) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def get(self, name: str) -> ToolSpec:
        if name not in self._specs:
            raise KeyError(f"tool '{name}' not registered")
        return self._specs[name]

    def get_handler(self, name: str) -> Callable[..., Any]:
        if name not in self._handlers:
            raise KeyError(f"handler for tool '{name}' not registered")
        return self._handlers[name]

    def list_all(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def list_for(
        self,
        *,
        agent: str = "",
        surface: str = "",
        allowed_modes: list[str] | None = None,
    ) -> list[ToolSpec]:
        modes = allowed_modes or []
        result: list[ToolSpec] = []
        for spec in self._specs.values():
            if not spec.enabled:
                continue
            if spec.agent_scope and agent and agent not in spec.agent_scope:
                continue
            if spec.surfaces and surface and surface not in spec.surfaces:
                continue
            if spec.mode == "action" and "action" not in modes:
                continue
            result.append(spec)
        return result

    def __contains__(self, name: str) -> bool:
        return name in self._specs

    def __len__(self) -> int:
        return len(self._specs)
