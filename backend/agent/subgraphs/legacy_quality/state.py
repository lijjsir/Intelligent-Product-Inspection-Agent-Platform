from __future__ import annotations

from typing import Any, TypedDict

from agent.contracts import AgentOutput


class LegacyQualityState(TypedDict, total=False):
    output: AgentOutput
    raw_state: dict[str, Any]
