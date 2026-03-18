from typing import Dict


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, dict] = {}

    def register(self, tool_manifest: dict) -> None:
        self._tools[tool_manifest["name"]] = tool_manifest

    def get(self, name: str) -> dict | None:
        return self._tools.get(name)
