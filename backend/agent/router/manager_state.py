from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent.router.contracts import AgentArtifact, AgentObservation, AgentRoutePlan


class ManagerState(BaseModel):
    request_id: str
    workflow_run_id: str
    surface: str = "chat"

    original_query: str
    normalized_query: str = ""

    org_id: str
    user_id: str | None = None
    session_id: str | None = None

    attachments: list[dict[str, Any]] = Field(default_factory=list)
    history_messages: list[dict[str, Any]] = Field(default_factory=list)
    selected_rag_space: dict[str, Any] | None = None
    rag_scope: dict[str, Any] | None = None

    allowed_modes: list[str] = Field(default_factory=lambda: ["answer", "report"])
    forbidden_modes: list[str] = Field(default_factory=list)

    action_intent: str | None = None
    goal: str = ""
    constraints: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    manager_model: dict[str, Any] | None = None
    manager_model_runtime: dict[str, Any] | None = Field(default=None, exclude=True)

    route_plan: AgentRoutePlan | None = None

    observations: list[AgentObservation] = Field(default_factory=list)
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)

    iteration: int = 0
    max_iterations: int = 3
    max_tool_calls: int = 5
    max_llm_calls: int = 3
    timeout_ms: int = 45000

    used_tool_calls: int = 0
    used_llm_calls: int = 0

    satisfied: bool = False
    satisfaction_score: float = 0.0
    final_action: str = "continue"

    selected_agent: str = ""
    executed_step_hashes: set[str] = Field(default_factory=set)
    route_plan_hashes: list[str] = Field(default_factory=list)
    last_artifact_counts: list[int] = Field(default_factory=list)

    # Tool system — injected by ManagerDispatcher at execution time
    available_tools: list[Any] = Field(default_factory=list, exclude=True)
    forced_tool_names: list[str] = Field(default_factory=list, exclude=True)
    tool_invoker: Any = Field(default=None, exclude=True)
