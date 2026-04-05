from __future__ import annotations

from typing import Any, TypedDict

from agent.contracts import AgentOutput, ClarificationRequest, PersistableOutput


class LLMNativeQualityState(TypedDict, total=False):
    parsed_files: list[dict[str, Any]]
    missing_fields: list[str]
    clarification: ClarificationRequest
    answer: str
    citations: list[dict[str, Any]]
    quality: dict[str, Any]
    persistable_output: PersistableOutput
    output: AgentOutput
