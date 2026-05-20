"""Neutral runtime profile stubs.

These helpers keep the runtime profile contract stable for agent subgraphs
after the retired optimization layer was removed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeProfileTarget:
    target_key: str = ""
    subgraph_key: str = ""
    node_id: str = ""
    node_label: str = ""
    module_name: str = ""
    optimization_goal: str = ""
    optimizer_strategy: str = "bootstrap-fewshot"
    compiler_version: str | None = None
    artifact_version: str | None = None
    prompt_version_id: str | None = None
    prompt_name: str | None = None
    prompt_content: str | None = None
    metric_names: list[str] = field(default_factory=list)
    config_payload: dict[str, Any] = field(default_factory=dict)
    is_enabled: bool = False


@dataclass(slots=True)
class RuntimeProfileMeta:
    compiler_version: str | None = None
    active_prompt_version: str | None = None
    targets: dict[str, RuntimeProfileTarget] = field(default_factory=dict)
    generation: str = "disabled"

    def as_metadata(self) -> dict[str, Any]:
        return {
            "compiler_version": self.compiler_version,
            "generation": self.generation,
            "active_prompt_version": self.active_prompt_version,
            "targets": {
                key: {
                    "target_key": target.target_key,
                    "node_label": target.node_label,
                    "artifact_version": target.artifact_version,
                    "is_enabled": target.is_enabled,
                    "config_payload": target.config_payload,
                }
                for key, target in self.targets.items()
            },
        }

    def get(self, target_key: str) -> RuntimeProfileTarget | None:
        return self.targets.get(target_key)


async def resolve_runtime_profile(org_id: str, subgraph_key: str) -> RuntimeProfileMeta:
    return RuntimeProfileMeta(
        generation="disabled",
        active_prompt_version=None,
    )


def build_runtime_prompt_section(profile: RuntimeProfileMeta, target_keys: list[str]) -> str:
    return ""
