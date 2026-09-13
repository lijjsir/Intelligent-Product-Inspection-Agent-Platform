from __future__ import annotations

from typing import Any, ClassVar

from agent.adapters.base import BaseAgentAdapter
from agent.adapters.llm_adapter import LLMAgentAdapter
from agent.adapters.pipeline_adapter import PipelineAgentAdapter
from app.core.exceptions import AgentAdapterUnavailableError
from app.core.config import settings

SUPPORTED_ADAPTER_TYPES = frozenset({"llm", "pipeline"})


class AgentAdapterFactory:
    _adapters: ClassVar[dict[str, BaseAgentAdapter]] = {}

    @classmethod
    def ensure_supported(cls, adapter_type: str | None) -> str:
        normalized = str(adapter_type or "llm").strip().lower()
        if normalized == "pipeline" and not bool(getattr(settings, "pipeline_agent_enabled", False)):
            raise AgentAdapterUnavailableError(normalized)
        if normalized not in SUPPORTED_ADAPTER_TYPES:
            raise ValueError(f"Unknown adapter_type: {adapter_type}")
        return normalized

    @classmethod
    def get(cls, adapter_type: str) -> BaseAgentAdapter:
        normalized = cls.ensure_supported(adapter_type)
        if normalized not in cls._adapters:
            if normalized == "llm":
                cls._adapters[normalized] = LLMAgentAdapter()
            elif normalized == "pipeline":
                cls._adapters[normalized] = PipelineAgentAdapter()
            else:  # pragma: no cover - guarded by ensure_supported
                raise ValueError(f"Unknown adapter_type: {adapter_type}")
        return cls._adapters[normalized]

    @classmethod
    def get_for_agent(cls, agent_def: Any) -> BaseAgentAdapter:
        adapter_type = getattr(agent_def, "adapter_type", "llm") or "llm"
        return cls.get(adapter_type)
