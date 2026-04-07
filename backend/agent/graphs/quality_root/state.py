from __future__ import annotations

from typing import Any, TypedDict

from agent.contracts import AgentOutput, NormalizedRequest, PersistableOutput, RouteDecision, RouteSignals


class QualityRootState(TypedDict, total=False):
    request: NormalizedRequest
    route_signals: RouteSignals
    route_decision: RouteDecision
    agent_output: AgentOutput
    persistable_output: PersistableOutput
    raw_subgraph_state: dict[str, Any]
