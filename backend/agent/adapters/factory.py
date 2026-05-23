from __future__ import annotations

from typing import Any

from agent.adapters.base import BaseAgentAdapter
from agent.adapters.llm_adapter import LLMAgentAdapter
from agent.adapters.pipeline_adapter import PipelineAgentAdapter


class AgentAdapterFactory:
    _adapters: dict[str, BaseAgentAdapter] = {}

    @classmethod
    def get(cls, adapter_type: str) -> BaseAgentAdapter:
        if adapter_type not in cls._adapters:
            if adapter_type == "llm":
                cls._adapters[adapter_type] = LLMAgentAdapter()
            elif adapter_type == "pipeline":
                cls._adapters[adapter_type] = PipelineAgentAdapter()
            else:
                raise ValueError(f"Unknown adapter_type: {adapter_type}")
        return cls._adapters[adapter_type]

    @classmethod
    def get_for_agent(cls, agent_def: Any) -> BaseAgentAdapter:
        adapter_type = getattr(agent_def, "adapter_type", "llm") or "llm"
        return cls.get(adapter_type)
