from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any
import uuid

from app.repositories.agent_ops_repo import DSPyOptimizationConfigRepository, PromptVersionRepository
from infra.database.session import get_session

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DSPyRuntimeTarget:
    target_key: str
    subgraph_key: str
    node_id: str
    node_label: str
    module_name: str
    optimization_goal: str
    optimizer_strategy: str
    compiler_version: str | None
    artifact_version: str | None
    prompt_version_id: str | None
    prompt_name: str | None
    prompt_content: str | None
    metric_names: list[str] = field(default_factory=list)
    config_payload: dict[str, Any] = field(default_factory=dict)
    is_enabled: bool = False

    def summary(self) -> dict[str, Any]:
        return {
            "target_key": self.target_key,
            "subgraph_key": self.subgraph_key,
            "node_id": self.node_id,
            "node_label": self.node_label,
            "module_name": self.module_name,
            "optimization_goal": self.optimization_goal,
            "artifact_version": self.artifact_version,
            "prompt_version_id": self.prompt_version_id,
            "prompt_name": self.prompt_name,
            "prompt_content": self.prompt_content,
            "optimizer_strategy": self.optimizer_strategy,
            "metric_names": list(self.metric_names),
            "config_payload": dict(self.config_payload),
            "is_enabled": self.is_enabled,
        }


@dataclass(slots=True)
class DSPyRuntimeProfile:
    org_id: str
    subgraph_key: str
    targets: dict[str, DSPyRuntimeTarget] = field(default_factory=dict)

    @property
    def active_prompt_version(self) -> str:
        versions = [
            target.artifact_version
            for target in self.targets.values()
            if target.is_enabled and target.artifact_version
        ]
        return ", ".join(sorted(set(versions))) if versions else f"builtin-{self.subgraph_key}-v1"

    def get(self, target_key: str) -> DSPyRuntimeTarget | None:
        return self.targets.get(target_key)

    def as_metadata(self) -> dict[str, Any]:
        return {
            "subgraph_key": self.subgraph_key,
            "active_prompt_version": self.active_prompt_version,
            "targets": {
                key: target.summary()
                for key, target in self.targets.items()
                if target.is_enabled
            },
        }


async def resolve_dspy_runtime_profile(org_id: str, subgraph_key: str) -> DSPyRuntimeProfile:
    try:
        uuid.UUID(str(org_id))
    except Exception:
        return DSPyRuntimeProfile(org_id=org_id, subgraph_key=subgraph_key, targets={})
    try:
        async with get_session() as session:
            optimization_repo = DSPyOptimizationConfigRepository(session, org_id)
            prompt_repo = PromptVersionRepository(session, org_id)
            configs = await optimization_repo.list_all()

            targets: dict[str, DSPyRuntimeTarget] = {}
            for config in configs:
                if str(config.subgraph_key) != subgraph_key:
                    continue
                prompt = None
                if config.current_prompt_version_id:
                    prompt = await prompt_repo.get(str(config.current_prompt_version_id))
                target = DSPyRuntimeTarget(
                    target_key=str(config.target_key),
                    subgraph_key=str(config.subgraph_key),
                    node_id=str(config.node_id),
                    node_label=str(config.node_label),
                    module_name=str(config.module_name),
                    optimization_goal=str(config.optimization_goal),
                    optimizer_strategy=str(config.optimizer_strategy),
                    compiler_version=config.compiler_version,
                    artifact_version=config.current_artifact_version,
                    prompt_version_id=str(config.current_prompt_version_id) if config.current_prompt_version_id else None,
                    prompt_name=str(prompt.name) if prompt else None,
                    prompt_content=str(prompt.content) if prompt else None,
                    metric_names=list(config.metric_names or []),
                    config_payload=dict(config.config_payload or {}),
                    is_enabled=bool(config.is_enabled and config.is_active_target),
                )
                targets[target.target_key] = target
            return DSPyRuntimeProfile(org_id=org_id, subgraph_key=subgraph_key, targets=targets)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning(
            "resolve_dspy_runtime_profile fallback org_id=%s subgraph_key=%s error=%s",
            org_id,
            subgraph_key,
            exc,
        )
        return DSPyRuntimeProfile(org_id=org_id, subgraph_key=subgraph_key, targets={})


def build_runtime_prompt_section(
    profile: DSPyRuntimeProfile,
    target_keys: list[str],
) -> str:
    sections: list[str] = []
    for target_key in target_keys:
        target = profile.get(target_key)
        if not target or not target.is_enabled:
            continue
        lines = [
            f"Target: {target.target_key}",
            f"Artifact: {target.artifact_version or 'builtin'}",
            f"Goal: {target.optimization_goal}",
        ]
        if target.metric_names:
            lines.append(f"Metrics: {', '.join(target.metric_names)}")
        if target.prompt_content:
            lines.append("Compiled Instructions:")
            lines.append(target.prompt_content.strip())
        elif target.config_payload:
            lines.append(f"Config Payload: {target.config_payload}")
        sections.append("\n".join(lines))
    if not sections:
        return ""
    return (
        "DSPy runtime optimization instructions are active for this response. "
        "Treat the following compiled targets as higher-priority execution guidance.\n\n"
        + "\n\n".join(sections)
    )
