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
    task_id: str | None = None
    session_id: str | None = None
    assistant_message_id: str | None = None
    trace_id: str | None = None
    trace_url: str | None = None

    attachments: list[dict[str, Any]] = Field(default_factory=list)
    request_ext: dict[str, Any] = Field(default_factory=dict)
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    history_messages: list[dict[str, Any]] = Field(default_factory=list)
    inspection_context: dict[str, Any] | None = None
    selected_rag_space: dict[str, Any] | None = None
    rag_scope: dict[str, Any] | None = None
    shared_memory_context: dict[str, Any] | None = None
    memory_sources: list[dict[str, Any]] = Field(default_factory=list)
    blackboard_context: dict[str, Any] | None = None
    blackboard_snapshot: dict[str, Any] | None = None
    agent_local_memory_context: list[dict[str, Any]] = Field(default_factory=list)
    agent_local_memory_owner: str | None = None
    conversation_summary: str | None = None
    session_facts: dict[str, Any] = Field(default_factory=dict)
    pending_action: dict[str, Any] | None = None
    short_term_memory: dict[str, Any] | None = None
    force_web_search: bool = False
    template_id: str | None = None

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
    llm_metas: list[dict[str, Any]] = Field(default_factory=list)
    llm_usage_events: list[dict[str, Any]] = Field(default_factory=list)

    iteration: int = 0
    max_iterations: int = 3
    max_tool_calls: int = 5
    max_llm_calls: int = 3
    timeout_ms: int = 45000

    used_tool_calls: int = 0
    used_llm_calls: int = 0
    used_plan_steps: int = 0

    satisfied: bool = False
    satisfaction_score: float = 0.0
    final_action: str = "continue"

    selected_agent: str = ""
    current_step_id: str | None = None
    current_capability: str | None = None
    current_owner_agent: str | None = None
    executed_step_hashes: set[str] = Field(default_factory=set)
    route_plan_hashes: list[str] = Field(default_factory=list)
    last_artifact_counts: list[int] = Field(default_factory=list)

    # Tool system — injected by ManagerDispatcher at execution time
    available_tools: list[Any] = Field(default_factory=list, exclude=True)
    forced_tool_names: list[str] = Field(default_factory=list, exclude=True)
    tool_invoker: Any = Field(default=None, exclude=True)


# Public architecture name; ManagerState remains as a compatibility alias.
OrchestrationState = ManagerState
