from dataclasses import dataclass


@dataclass(frozen=True)
class ToolRegistry:
    id: str
    name: str
    display_name: str
