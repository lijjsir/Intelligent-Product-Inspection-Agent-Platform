# Multi-Agent LangGraph Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the DOCX-defined parent-graph and multi-Agent architecture into a working LangGraph runtime where `MemoryManagerGraph` plans, routes, invokes child Agents, gates memory writes, and triggers governance recovery.

**Architecture:** Implement contracts first, then make the parent graph executable, then connect `QualityJudgementAgent` as the first real child Agent. The remaining professional Agents get runnable skeleton subgraphs and topology entries so the system has a complete shape before domain-specific business logic is filled in.

**Tech Stack:** Python 3.11, FastAPI service layer, Pydantic v2 contracts, LangGraph `StateGraph`, pytest, existing LLM gateway/client, existing Service/Repository persistence boundaries.

---

## Scope Notes

This plan covers the first implementation cycle from the approved design spec:

- Parent graph runtime and contracts.
- `QualityJudgementAgent` connected as the first real child Agent.
- Runnable skeletons for market, opinion, trend, sampling, lab, and governance child Agents.
- Model policy and secret-safety verification.
- Topology and Agent Ops alignment.

It does not implement full business logic for market monitoring, public opinion, trend evolution, supervision sampling, or lab detection. Those Agents become runnable contract-compliant skeletons with deterministic outputs and tests.

## File Structure

Create or modify these files:

- Create: `backend/agent/contracts/agent_runtime_contracts.py`
  - Owns `AgentKey`, `ModelPolicy`, `AgentRequest`, `MemoryCandidate`, `ExecutionPlanStep`, `ExecutionPlan`.
- Modify: `backend/agent/contracts/quality_contracts.py`
  - Extends `AgentOutput` with `memory_candidates`, `warnings`, `model_usage`, and `trace`.
- Modify: `backend/agent/contracts/__init__.py`
  - Exports runtime contracts.
- Create: `backend/agent/llm/model_policy.py`
  - Maps node use cases to DeepSeek, existing multimodal provider, existing embedding provider, or no model.
- Modify: `backend/agent/llm/client.py`
  - Keeps existing provider support, fixes provider-specific missing-key error text, and exposes `provider`.
- Modify: `backend/app/core/config.py`
  - Removes hardcoded default provider keys and relies on environment variables.
- Create: `backend/agent/subgraphs/skeleton.py`
  - Shared LangGraph skeleton factory for planned child Agents.
- Create: `backend/agent/subgraphs/market_monitor/__init__.py`
- Create: `backend/agent/subgraphs/market_monitor/graph.py`
- Create: `backend/agent/subgraphs/public_opinion/__init__.py`
- Create: `backend/agent/subgraphs/public_opinion/graph.py`
- Create: `backend/agent/subgraphs/trend_evolution/__init__.py`
- Create: `backend/agent/subgraphs/trend_evolution/graph.py`
- Create: `backend/agent/subgraphs/supervision_sampling/__init__.py`
- Create: `backend/agent/subgraphs/supervision_sampling/graph.py`
- Create: `backend/agent/subgraphs/lab_detection/__init__.py`
- Create: `backend/agent/subgraphs/lab_detection/graph.py`
- Create: `backend/agent/subgraphs/governance_recovery/__init__.py`
- Create: `backend/agent/subgraphs/governance_recovery/graph.py`
- Modify: `backend/agent/subgraphs/__init__.py`
  - Exports all child Agent classes.
- Create: `backend/agent/graphs/memory_manager/registry.py`
  - Maps Agent keys to child Agent runners.
- Modify: `backend/agent/graphs/memory_manager/state.py`
  - Adds request, routing, execution plan, child output, and final output fields.
- Modify: `backend/agent/graphs/memory_manager/nodes.py`
  - Adds request understanding, planning, routing, child invocation, aggregation, and memory candidate extraction.
- Modify: `backend/agent/graphs/memory_manager/graph.py`
  - Rewires graph topology and implements `run()`.
- Modify: `backend/agent/graphs/memory_manager/policy.py`
  - Extends route signals beyond `quality_judgement` while preserving existing quality defaults.
- Modify: `backend/agent/topology_catalog.py`
  - Aligns Agent Ops topology with runtime topology.
- Modify: `backend/app/services/quality_agent_orchestrator_service.py`
  - Keeps the existing `MemoryManagerGraph().run(request)` call and validates the response contract.
- Test: `backend/tests/test_agent_runtime_contracts.py`
- Test: `backend/tests/test_model_policy.py`
- Test: `backend/tests/test_child_agent_skeletons.py`
- Test: `backend/tests/test_memory_manager_graph_runtime.py`
- Test: `backend/tests/test_quality_agent_orchestrator_service.py`
- Test: `backend/tests/test_agent_ops_api.py`

---

## Task 1: Runtime Contracts

**Files:**
- Create: `backend/agent/contracts/agent_runtime_contracts.py`
- Modify: `backend/agent/contracts/quality_contracts.py`
- Modify: `backend/agent/contracts/__init__.py`
- Test: `backend/tests/test_agent_runtime_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Create `backend/tests/test_agent_runtime_contracts.py`:

```python
from agent.contracts import (
    AgentOutput,
    AgentRequest,
    ExecutionPlan,
    ExecutionPlanStep,
    MemoryCandidate,
    ModelPolicy,
    NormalizedAttachment,
    NormalizedRequest,
)


def test_agent_request_round_trips_to_normalized_request():
    request = AgentRequest(
        request_id="req-1",
        workflow_run_id="wf-1",
        parent_trace_id="trace-parent",
        org_id="org-1",
        user_id="user-1",
        workspace="app",
        request_kind="chat",
        query="检测这张图片",
        attachments=[NormalizedAttachment(name="a.png", url="https://example.com/a.png", kind="image")],
        image_urls=["https://example.com/a.png"],
        product_id="P-1",
        spec_code="SPEC-1",
        selected_rag_space={"id": "rag-1", "name": "标准库"},
        memory_context={"items": [{"memory_id": "mem-1"}]},
        model_policy=ModelPolicy(use_case="vision", provider="volcengine"),
    )

    normalized = request.to_normalized_request()

    assert isinstance(normalized, NormalizedRequest)
    assert normalized.request_id == "req-1"
    assert normalized.workflow_run_id == "wf-1"
    assert normalized.org_id == "org-1"
    assert normalized.image_urls == ["https://example.com/a.png"]
    assert normalized.ext["selected_rag_space"] == {"id": "rag-1", "name": "标准库"}
    assert normalized.ext["memory_context"] == {"items": [{"memory_id": "mem-1"}]}
    assert normalized.ext["parent_trace_id"] == "trace-parent"


def test_execution_plan_accepts_multiple_child_agents():
    plan = ExecutionPlan(
        steps=[
            ExecutionPlanStep(step_id="step-1", agent_key="market_monitor", reason="市场异常"),
            ExecutionPlanStep(step_id="step-2", agent_key="quality_judgement", reason="质量判定"),
        ],
        parallelizable=False,
    )

    assert [step.agent_key for step in plan.steps] == ["market_monitor", "quality_judgement"]
    assert plan.primary_agent_key == "market_monitor"


def test_agent_output_carries_memory_candidates_and_trace():
    candidate = MemoryCandidate(
        memory_id="mem-1",
        memory_type="task_episode",
        source_agent="quality_judgement",
        source_trace_id="trace-1",
        source_evidence=[{"id": "doc-1"}],
        scope={"org_id": "org-1"},
        content={"summary": "合格"},
        confidence=0.91,
        trust_policy={"readable_after_gate": True},
        dependency_refs=["doc-1"],
        permission_scope={"workspace": "app"},
    )
    output = AgentOutput(
        answer="完成",
        memory_candidates=[candidate.model_dump()],
        warnings=["specialized_agent_unavailable"],
        model_usage=[{"provider": "deepseek", "model_id": "deepseek-v4-flash"}],
        trace={"trace_id": "trace-1", "source_agent": "quality_judgement"},
    )

    assert output.memory_candidates[0]["memory_id"] == "mem-1"
    assert output.warnings == ["specialized_agent_unavailable"]
    assert output.model_usage[0]["provider"] == "deepseek"
    assert output.trace["source_agent"] == "quality_judgement"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_agent_runtime_contracts.py -q
```

Expected: FAIL because `AgentRequest`, `ExecutionPlan`, `ExecutionPlanStep`, `MemoryCandidate`, and `ModelPolicy` are not exported yet.

- [ ] **Step 3: Add runtime contracts**

Create `backend/agent/contracts/agent_runtime_contracts.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.contracts.quality_contracts import NormalizedAttachment, NormalizedRequest


AgentKey = Literal[
    "market_monitor",
    "public_opinion",
    "trend_evolution",
    "supervision_sampling",
    "lab_detection",
    "quality_judgement",
    "governance_recovery",
]

ModelUseCase = Literal["text", "vision", "embedding", "tool_only"]
ModelProvider = Literal["deepseek", "volcengine", "none"]


class ModelPolicy(BaseModel):
    use_case: ModelUseCase = "text"
    provider: ModelProvider = "deepseek"
    model_id: str | None = None
    base_url: str | None = None
    reason: str = ""


class AgentRequest(BaseModel):
    request_id: str
    workflow_run_id: str | None = None
    parent_trace_id: str | None = None
    org_id: str
    user_id: str | None = None
    workspace: str = "app"
    plan_tier: str = "basic"
    capabilities: list[str] = Field(default_factory=list)
    request_kind: Literal["chat", "task"] = "chat"
    query: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    ext: dict[str, Any] = Field(default_factory=dict)
    attachments: list[NormalizedAttachment] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    product_id: str | None = None
    spec_code: str | None = None
    selected_rag_space: dict[str, Any] | None = None
    memory_context: dict[str, Any] = Field(default_factory=dict)
    route_hints: dict[str, Any] = Field(default_factory=dict)
    task_context: dict[str, Any] = Field(default_factory=dict)
    model_policy: ModelPolicy = Field(default_factory=ModelPolicy)

    def to_normalized_request(self) -> NormalizedRequest:
        ext = dict(self.ext)
        if self.selected_rag_space is not None:
            ext["selected_rag_space"] = self.selected_rag_space
        if self.memory_context:
            ext["memory_context"] = self.memory_context
        if self.parent_trace_id:
            ext["parent_trace_id"] = self.parent_trace_id
        ext["model_policy"] = self.model_policy.model_dump()
        return NormalizedRequest(
            request_kind=self.request_kind,
            request_id=self.request_id,
            workflow_run_id=self.workflow_run_id,
            org_id=self.org_id,
            user_id=self.user_id,
            workspace=self.workspace,
            plan_tier=self.plan_tier,
            capabilities=list(self.capabilities),
            query=self.query,
            metadata=dict(self.metadata),
            ext=ext,
            attachments=list(self.attachments),
            product_id=self.product_id,
            spec_code=self.spec_code,
            image_urls=list(self.image_urls),
            route_hints=dict(self.route_hints),
        )


class ExecutionPlanStep(BaseModel):
    step_id: str
    agent_key: AgentKey
    reason: str
    depends_on: list[str] = Field(default_factory=list)
    input_overrides: dict[str, Any] = Field(default_factory=dict)
    model_policy: ModelPolicy = Field(default_factory=ModelPolicy)


class ExecutionPlan(BaseModel):
    steps: list[ExecutionPlanStep] = Field(default_factory=list)
    parallelizable: bool = False
    reason: str = ""

    @property
    def primary_agent_key(self) -> AgentKey | None:
        if not self.steps:
            return None
        return self.steps[0].agent_key


class MemoryCandidate(BaseModel):
    memory_id: str | None = None
    memory_type: str
    source_agent: AgentKey | str
    source_trace_id: str | None = None
    source_evidence: list[dict[str, Any]] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    content: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    trust_policy: dict[str, Any] = Field(default_factory=dict)
    dependency_refs: list[str] = Field(default_factory=list)
    permission_scope: dict[str, Any] = Field(default_factory=dict)
    status: Literal["candidate"] = "candidate"
```

- [ ] **Step 4: Extend `AgentOutput`**

Modify `backend/agent/contracts/quality_contracts.py` by adding these fields to `AgentOutput`:

```python
    memory_candidates: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_usage: list[dict[str, Any]] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
```

Place the fields after `persistable_output`.

- [ ] **Step 5: Widen route decision subgraph keys**

Modify `backend/agent/contracts/quality_contracts.py`.

Replace:

```python
class RouteDecision(BaseModel):
    mode: Literal["legacy_only", "canary_non_pdf", "router_enabled"] = "legacy_only"
    selected_subgraph: Literal["quality_judgement"] = "quality_judgement"
    fallback_subgraph: Literal["quality_judgement"] = "quality_judgement"
```

with:

```python
class RouteDecision(BaseModel):
    mode: Literal["legacy_only", "canary_non_pdf", "router_enabled"] = "legacy_only"
    selected_subgraph: str = "quality_judgement"
    fallback_subgraph: str = "quality_judgement"
```

- [ ] **Step 6: Export runtime contracts**

Modify `backend/agent/contracts/__init__.py`:

```python
from agent.contracts.agent_runtime_contracts import (
    AgentKey,
    AgentRequest,
    ExecutionPlan,
    ExecutionPlanStep,
    MemoryCandidate,
    ModelPolicy,
)
```

Add the same names to `__all__`.

- [ ] **Step 7: Run tests**

Run:

```bash
cd backend
pytest tests/test_agent_runtime_contracts.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/agent/contracts/agent_runtime_contracts.py backend/agent/contracts/quality_contracts.py backend/agent/contracts/__init__.py backend/tests/test_agent_runtime_contracts.py
git commit -m "feat: add agent runtime contracts"
```

---

## Task 2: Model Policy And Secret-Safe Defaults

**Files:**
- Create: `backend/agent/llm/model_policy.py`
- Modify: `backend/agent/llm/client.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_model_policy.py`
- Test: `backend/tests/test_governance_logic.py`

- [ ] **Step 1: Write failing model policy tests**

Create `backend/tests/test_model_policy.py`:

```python
import pytest

from agent.contracts import ModelPolicy
from agent.llm.model_policy import client_from_policy, default_model_policy
from app.core.config import settings


def test_default_policy_selects_deepseek_for_text():
    policy = default_model_policy("text", reason="planner")
    assert policy.provider == "deepseek"
    assert policy.use_case == "text"
    assert policy.model_id == settings.deepseek_model_id
    assert policy.reason == "planner"


def test_default_policy_selects_volcengine_for_vision():
    policy = default_model_policy("vision", reason="defect detection")
    assert policy.provider == "volcengine"
    assert policy.use_case == "vision"
    assert policy.model_id == settings.volcengine_model_id


def test_default_policy_selects_volcengine_for_embedding():
    policy = default_model_policy("embedding", reason="rag")
    assert policy.provider == "volcengine"
    assert policy.use_case == "embedding"
    assert policy.model_id == settings.volcengine_embed_model


def test_default_policy_selects_none_for_tool_only():
    policy = default_model_policy("tool_only", reason="local parser")
    assert policy.provider == "none"
    assert policy.use_case == "tool_only"
    assert policy.model_id is None


def test_client_from_policy_uses_deepseek_provider(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "unit-test-key")
    client = client_from_policy(
        ModelPolicy(use_case="text", provider="deepseek", model_id="deepseek-v4-flash"),
        trace_id="trace-1",
        task_id="task-1",
        org_id="org-1",
    )

    assert client.provider == "deepseek"
    assert client.model_id == "deepseek-v4-flash"


def test_client_from_policy_rejects_tool_only_policy():
    with pytest.raises(ValueError, match="tool_only"):
        client_from_policy(ModelPolicy(use_case="tool_only", provider="none"))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_model_policy.py -q
```

Expected: FAIL because `agent.llm.model_policy` does not exist.

- [ ] **Step 3: Add model policy helper**

Create `backend/agent/llm/model_policy.py`:

```python
from __future__ import annotations

from agent.contracts import ModelPolicy, ModelUseCase
from agent.llm.client import LLMClient
from app.core.config import settings


def default_model_policy(use_case: ModelUseCase = "text", *, reason: str = "") -> ModelPolicy:
    if use_case == "text":
        return ModelPolicy(
            use_case="text",
            provider="deepseek",
            model_id=settings.deepseek_model_id,
            base_url=settings.deepseek_base_url,
            reason=reason,
        )
    if use_case == "vision":
        return ModelPolicy(
            use_case="vision",
            provider="volcengine",
            model_id=settings.volcengine_model_id,
            base_url=settings.volcengine_base_url,
            reason=reason,
        )
    if use_case == "embedding":
        return ModelPolicy(
            use_case="embedding",
            provider="volcengine",
            model_id=settings.volcengine_embed_model,
            base_url=settings.volcengine_base_url,
            reason=reason,
        )
    return ModelPolicy(use_case="tool_only", provider="none", model_id=None, reason=reason)


def client_from_policy(
    policy: ModelPolicy,
    *,
    trace_id: str | None = None,
    task_id: str | None = None,
    org_id: str | None = None,
) -> LLMClient:
    if policy.provider == "none" or policy.use_case == "tool_only":
        raise ValueError("tool_only model policy does not create an LLMClient")
    return LLMClient(
        provider=policy.provider,
        base_url=policy.base_url,
        model_id=policy.model_id,
        trace_id=trace_id,
        task_id=task_id,
        org_id=org_id,
    )
```

- [ ] **Step 4: Expose `LLMClient.provider` and improve missing-key error**

Modify `backend/agent/llm/client.py`:

```python
    @property
    def provider(self) -> str:
        return self._provider
```

Place it above the existing `model_id` property.

Modify `_post_json()` missing key check:

```python
        if not self._api_key:
            env_name = "DEEPSEEK_API_KEY" if self._provider == "deepseek" else "VOLCENGINE_API_KEY"
            raise RuntimeError(f"{env_name} is not configured")
```

- [ ] **Step 5: Remove hardcoded provider key defaults**

Modify `backend/app/core/config.py`:

```python
    volcengine_api_key: str = ""
```

Keep these existing fields:

```python
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model_id: str = "deepseek-v4-flash"
```

For local development, set secrets in the gitignored backend `.env` file using the existing `PIAP_` prefix:

```text
PIAP_VOLCENGINE_API_KEY=your-local-volcengine-key
PIAP_DEEPSEEK_API_KEY=your-local-deepseek-key
```

- [ ] **Step 6: Add DeepSeek coverage to existing LLM client tests**

Append to `backend/tests/test_governance_logic.py`:

```python
@pytest.mark.asyncio
async def test_llm_client_deepseek_missing_key_message(monkeypatch):
    monkeypatch.setattr("agent.llm.client.settings.deepseek_api_key", "")
    client = LLMClient(provider="deepseek", model_id="deepseek-v4-flash")

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY is not configured"):
        await client.chat([{"role": "user", "content": "hi"}])
```

- [ ] **Step 7: Run tests**

Run:

```bash
cd backend
pytest tests/test_model_policy.py tests/test_governance_logic.py::test_llm_client_deepseek_missing_key_message -q
```

Expected: PASS.

- [ ] **Step 8: Scan for leaked keys**

Run:

```bash
rg -n "api_key\\s*=\\s*['\\\"][A-Za-z0-9_-]{20,}|DEEPSEEK_API_KEY\\s*=\\s*[A-Za-z0-9_-]{20,}|VOLCENGINE_API_KEY\\s*=\\s*[A-Za-z0-9_-]{20,}" backend docs --glob '!runtime_uploads/**'
```

Expected: no live key values in backend code or docs. If the old Volcengine key appears in committed config, remove it before committing.

- [ ] **Step 9: Commit**

```bash
git add backend/agent/llm/model_policy.py backend/agent/llm/client.py backend/app/core/config.py backend/tests/test_model_policy.py backend/tests/test_governance_logic.py
git commit -m "feat: add model policy for child agents"
```

---

## Task 3: Child Agent Skeleton Subgraphs

**Files:**
- Create: `backend/agent/subgraphs/skeleton.py`
- Create: `backend/agent/subgraphs/market_monitor/__init__.py`
- Create: `backend/agent/subgraphs/market_monitor/graph.py`
- Create: `backend/agent/subgraphs/public_opinion/__init__.py`
- Create: `backend/agent/subgraphs/public_opinion/graph.py`
- Create: `backend/agent/subgraphs/trend_evolution/__init__.py`
- Create: `backend/agent/subgraphs/trend_evolution/graph.py`
- Create: `backend/agent/subgraphs/supervision_sampling/__init__.py`
- Create: `backend/agent/subgraphs/supervision_sampling/graph.py`
- Create: `backend/agent/subgraphs/lab_detection/__init__.py`
- Create: `backend/agent/subgraphs/lab_detection/graph.py`
- Create: `backend/agent/subgraphs/governance_recovery/__init__.py`
- Create: `backend/agent/subgraphs/governance_recovery/graph.py`
- Modify: `backend/agent/subgraphs/__init__.py`
- Test: `backend/tests/test_child_agent_skeletons.py`

- [ ] **Step 1: Write failing skeleton tests**

Create `backend/tests/test_child_agent_skeletons.py`:

```python
import pytest

from agent.contracts import AgentOutput, AgentRequest
from agent.subgraphs import (
    GovernanceRecoveryAgent,
    LabDetectionAgent,
    MarketMonitorAgent,
    PublicOpinionAgent,
    SupervisionSamplingAgent,
    TrendEvolutionAgent,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_cls", "agent_key"),
    [
        (MarketMonitorAgent, "market_monitor"),
        (PublicOpinionAgent, "public_opinion"),
        (TrendEvolutionAgent, "trend_evolution"),
        (SupervisionSamplingAgent, "supervision_sampling"),
        (LabDetectionAgent, "lab_detection"),
        (GovernanceRecoveryAgent, "governance_recovery"),
    ],
)
async def test_planned_child_agent_returns_contract_output(agent_cls, agent_key):
    request = AgentRequest(
        request_id=f"req-{agent_key}",
        workflow_run_id=f"wf-{agent_key}",
        parent_trace_id="trace-parent",
        org_id="org-1",
        user_id="user-1",
        query="请分析风险",
    )

    output = await agent_cls().run(request)

    assert isinstance(output, AgentOutput)
    assert output.message_type == "agent_result"
    assert output.action_state == "planned_agent_unavailable"
    assert output.trace["source_agent"] == agent_key
    assert output.warnings == ["specialized_agent_not_implemented"]
    assert output.persistable_output is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_child_agent_skeletons.py -q
```

Expected: FAIL because the skeleton Agents are not implemented or exported.

- [ ] **Step 3: Add shared skeleton graph factory**

Create `backend/agent/subgraphs/skeleton.py`:

```python
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from agent.contracts import AgentOutput, AgentRequest, PersistableOutput


class SkeletonAgentState(TypedDict, total=False):
    request: AgentRequest
    agent_key: str
    display_name: str
    plan: dict[str, Any]
    evidence: list[dict[str, Any]]
    review: dict[str, Any]
    output: AgentOutput


def _input_adapter(state: SkeletonAgentState) -> SkeletonAgentState:
    state["plan"] = {
        "status": "accepted",
        "query": state["request"].query,
        "message": f"{state['display_name']} received the request.",
    }
    return state


def _domain_planner(state: SkeletonAgentState) -> SkeletonAgentState:
    state["plan"] = {
        **dict(state.get("plan") or {}),
        "execution": "skeleton",
        "reason": "The specialized business logic is not active in this implementation cycle.",
    }
    return state


def _evidence_synthesizer(state: SkeletonAgentState) -> SkeletonAgentState:
    state["evidence"] = [
        {
            "id": f"{state['agent_key']}-placeholder",
            "kind": "skeleton",
            "quote": state["request"].query[:180],
        }
    ]
    return state


def _review_gate(state: SkeletonAgentState) -> SkeletonAgentState:
    state["review"] = {
        "passed": False,
        "risk_level": "medium",
        "reason": "specialized_agent_not_implemented",
    }
    return state


def _output_builder(state: SkeletonAgentState) -> SkeletonAgentState:
    agent_key = state["agent_key"]
    display_name = state["display_name"]
    state["output"] = AgentOutput(
        message_type="agent_result",
        answer=f"{display_name} 已接收请求，但当前仅启用可运行骨架，尚未启用完整专业逻辑。",
        summary=f"{display_name} skeleton output",
        citations=list(state.get("evidence") or []),
        quality=dict(state.get("review") or {}),
        action_state="planned_agent_unavailable",
        persistable_output=PersistableOutput(),
        warnings=["specialized_agent_not_implemented"],
        trace={
            "source_agent": agent_key,
            "parent_trace_id": state["request"].parent_trace_id,
            "workflow_run_id": state["request"].workflow_run_id,
        },
        raw_state={
            "plan": state.get("plan") or {},
            "review": state.get("review") or {},
        },
    )
    return state


class SkeletonSubgraphAgent:
    agent_key: str
    display_name: str

    def __init__(self, *, agent_key: str, display_name: str) -> None:
        self.agent_key = agent_key
        self.display_name = display_name
        graph = StateGraph(SkeletonAgentState)
        graph.add_node("input_adapter", _input_adapter)
        graph.add_node("domain_planner", _domain_planner)
        graph.add_node("evidence_synthesizer", _evidence_synthesizer)
        graph.add_node("review_gate", _review_gate)
        graph.add_node("output_builder", _output_builder)
        graph.set_entry_point("input_adapter")
        graph.add_edge("input_adapter", "domain_planner")
        graph.add_edge("domain_planner", "evidence_synthesizer")
        graph.add_edge("evidence_synthesizer", "review_gate")
        graph.add_edge("review_gate", "output_builder")
        graph.add_edge("output_builder", END)
        self._graph = graph.compile()

    async def run(self, request: AgentRequest) -> AgentOutput:
        state = await self._graph.ainvoke(
            {
                "request": request,
                "agent_key": self.agent_key,
                "display_name": self.display_name,
            }
        )
        return AgentOutput.model_validate(state["output"])
```

- [ ] **Step 4: Add market monitor Agent**

Create `backend/agent/subgraphs/market_monitor/graph.py`:

```python
from __future__ import annotations

from agent.subgraphs.skeleton import SkeletonSubgraphAgent


class MarketMonitorAgent(SkeletonSubgraphAgent):
    def __init__(self) -> None:
        super().__init__(agent_key="market_monitor", display_name="MarketMonitorAgent")
```

Create `backend/agent/subgraphs/market_monitor/__init__.py`:

```python
from agent.subgraphs.market_monitor.graph import MarketMonitorAgent

__all__ = ["MarketMonitorAgent"]
```

- [ ] **Step 5: Add public opinion Agent**

Create `backend/agent/subgraphs/public_opinion/graph.py`:

```python
from __future__ import annotations

from agent.subgraphs.skeleton import SkeletonSubgraphAgent


class PublicOpinionAgent(SkeletonSubgraphAgent):
    def __init__(self) -> None:
        super().__init__(agent_key="public_opinion", display_name="PublicOpinionAgent")
```

Create `backend/agent/subgraphs/public_opinion/__init__.py`:

```python
from agent.subgraphs.public_opinion.graph import PublicOpinionAgent

__all__ = ["PublicOpinionAgent"]
```

- [ ] **Step 6: Add trend evolution Agent**

Create `backend/agent/subgraphs/trend_evolution/graph.py`:

```python
from __future__ import annotations

from agent.subgraphs.skeleton import SkeletonSubgraphAgent


class TrendEvolutionAgent(SkeletonSubgraphAgent):
    def __init__(self) -> None:
        super().__init__(agent_key="trend_evolution", display_name="TrendEvolutionAgent")
```

Create `backend/agent/subgraphs/trend_evolution/__init__.py`:

```python
from agent.subgraphs.trend_evolution.graph import TrendEvolutionAgent

__all__ = ["TrendEvolutionAgent"]
```

- [ ] **Step 7: Add supervision sampling Agent**

Create `backend/agent/subgraphs/supervision_sampling/graph.py`:

```python
from __future__ import annotations

from agent.subgraphs.skeleton import SkeletonSubgraphAgent


class SupervisionSamplingAgent(SkeletonSubgraphAgent):
    def __init__(self) -> None:
        super().__init__(agent_key="supervision_sampling", display_name="SupervisionSamplingAgent")
```

Create `backend/agent/subgraphs/supervision_sampling/__init__.py`:

```python
from agent.subgraphs.supervision_sampling.graph import SupervisionSamplingAgent

__all__ = ["SupervisionSamplingAgent"]
```

- [ ] **Step 8: Add lab detection Agent**

Create `backend/agent/subgraphs/lab_detection/graph.py`:

```python
from __future__ import annotations

from agent.subgraphs.skeleton import SkeletonSubgraphAgent


class LabDetectionAgent(SkeletonSubgraphAgent):
    def __init__(self) -> None:
        super().__init__(agent_key="lab_detection", display_name="LabDetectionAgent")
```

Create `backend/agent/subgraphs/lab_detection/__init__.py`:

```python
from agent.subgraphs.lab_detection.graph import LabDetectionAgent

__all__ = ["LabDetectionAgent"]
```

- [ ] **Step 9: Add governance recovery child Agent shell**

Create `backend/agent/subgraphs/governance_recovery/graph.py`:

```python
from __future__ import annotations

from agent.subgraphs.skeleton import SkeletonSubgraphAgent


class GovernanceRecoveryAgent(SkeletonSubgraphAgent):
    def __init__(self) -> None:
        super().__init__(agent_key="governance_recovery", display_name="GovernanceRecoveryAgent")
```

Create `backend/agent/subgraphs/governance_recovery/__init__.py`:

```python
from agent.subgraphs.governance_recovery.graph import GovernanceRecoveryAgent

__all__ = ["GovernanceRecoveryAgent"]
```

- [ ] **Step 10: Export child Agents**

Modify `backend/agent/subgraphs/__init__.py`:

```python
from agent.subgraphs.governance_recovery import GovernanceRecoveryAgent
from agent.subgraphs.lab_detection import LabDetectionAgent
from agent.subgraphs.market_monitor import MarketMonitorAgent
from agent.subgraphs.public_opinion import PublicOpinionAgent
from agent.subgraphs.quality_chat import QualityChatGraph
from agent.subgraphs.quality_judgement import QualityJudgementSubgraph
from agent.subgraphs.supervision_sampling import SupervisionSamplingAgent
from agent.subgraphs.trend_evolution import TrendEvolutionAgent

__all__ = [
    "GovernanceRecoveryAgent",
    "LabDetectionAgent",
    "MarketMonitorAgent",
    "PublicOpinionAgent",
    "QualityChatGraph",
    "QualityJudgementSubgraph",
    "SupervisionSamplingAgent",
    "TrendEvolutionAgent",
]
```

- [ ] **Step 11: Run tests**

Run:

```bash
cd backend
pytest tests/test_child_agent_skeletons.py -q
```

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add backend/agent/subgraphs backend/tests/test_child_agent_skeletons.py
git commit -m "feat: add runnable child agent skeletons"
```

---

## Task 4: Child Agent Registry And Quality Judgement Adapter

**Files:**
- Create: `backend/agent/graphs/memory_manager/registry.py`
- Test: `backend/tests/test_memory_manager_graph_runtime.py`

- [ ] **Step 1: Write failing registry tests**

Create `backend/tests/test_memory_manager_graph_runtime.py` with the first tests:

```python
import pytest

from agent.contracts import AgentOutput, AgentRequest
from agent.graphs.memory_manager.registry import ChildAgentRegistry


@pytest.mark.asyncio
async def test_registry_invokes_quality_judgement(monkeypatch):
    calls = []

    class FakeQualityJudgementSubgraph:
        async def run(self, request):
            calls.append(request)
            return AgentOutput(answer="quality ok", trace={"source_agent": "quality_judgement"})

    monkeypatch.setattr(
        "agent.graphs.memory_manager.registry.QualityJudgementSubgraph",
        lambda: FakeQualityJudgementSubgraph(),
    )

    output = await ChildAgentRegistry().run(
        "quality_judgement",
        AgentRequest(request_id="req-1", org_id="org-1", query="质量问题"),
    )

    assert output.answer == "quality ok"
    assert calls[0].request_id == "req-1"


@pytest.mark.asyncio
async def test_registry_invokes_skeleton_agent():
    output = await ChildAgentRegistry().run(
        "market_monitor",
        AgentRequest(request_id="req-1", org_id="org-1", query="市场价格异常"),
    )

    assert output.trace["source_agent"] == "market_monitor"
    assert output.action_state == "planned_agent_unavailable"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_memory_manager_graph_runtime.py::test_registry_invokes_quality_judgement tests/test_memory_manager_graph_runtime.py::test_registry_invokes_skeleton_agent -q
```

Expected: FAIL because `registry.py` does not exist.

- [ ] **Step 3: Add child Agent registry**

Create `backend/agent/graphs/memory_manager/registry.py`:

```python
from __future__ import annotations

from agent.contracts import AgentKey, AgentOutput, AgentRequest
from agent.subgraphs import (
    LabDetectionAgent,
    MarketMonitorAgent,
    PublicOpinionAgent,
    QualityJudgementSubgraph,
    SupervisionSamplingAgent,
    TrendEvolutionAgent,
)


class ChildAgentRegistry:
    def __init__(self) -> None:
        self._skeletons = {
            "market_monitor": MarketMonitorAgent,
            "public_opinion": PublicOpinionAgent,
            "trend_evolution": TrendEvolutionAgent,
            "supervision_sampling": SupervisionSamplingAgent,
            "lab_detection": LabDetectionAgent,
        }

    async def run(self, agent_key: AgentKey, request: AgentRequest) -> AgentOutput:
        if agent_key == "quality_judgement":
            output = await QualityJudgementSubgraph().run(request.to_normalized_request())
            output.trace = {
                **dict(output.trace or {}),
                "source_agent": "quality_judgement",
                "parent_trace_id": request.parent_trace_id,
                "workflow_run_id": request.workflow_run_id,
            }
            return output
        agent_cls = self._skeletons.get(agent_key)
        if agent_cls is None:
            return AgentOutput(
                message_type="agent_result",
                answer=f"Unsupported child Agent: {agent_key}",
                summary="Unsupported child Agent",
                action_state="unsupported_agent",
                warnings=["unsupported_agent"],
                trace={"source_agent": str(agent_key), "parent_trace_id": request.parent_trace_id},
            )
        return await agent_cls().run(request)
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend
pytest tests/test_memory_manager_graph_runtime.py::test_registry_invokes_quality_judgement tests/test_memory_manager_graph_runtime.py::test_registry_invokes_skeleton_agent -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/graphs/memory_manager/registry.py backend/tests/test_memory_manager_graph_runtime.py
git commit -m "feat: add child agent registry"
```

---

## Task 5: MemoryManagerGraph Runtime

**Files:**
- Modify: `backend/agent/graphs/memory_manager/state.py`
- Modify: `backend/agent/graphs/memory_manager/nodes.py`
- Modify: `backend/agent/graphs/memory_manager/graph.py`
- Modify: `backend/agent/graphs/memory_manager/policy.py`
- Test: `backend/tests/test_memory_manager_graph_runtime.py`

- [ ] **Step 1: Add failing parent graph tests**

Append to `backend/tests/test_memory_manager_graph_runtime.py`:

```python
from agent.contracts import NormalizedRequest
from agent.graphs.memory_manager.graph import MemoryManagerGraph


@pytest.mark.asyncio
async def test_memory_manager_run_routes_to_quality_judgement(monkeypatch):
    class FakeRegistry:
        async def run(self, agent_key, request):
            assert agent_key == "quality_judgement"
            assert request.memory_context == {"items": [], "warnings": [], "degraded": False}
            return AgentOutput(
                answer="quality answer",
                summary="quality summary",
                trace={"source_agent": "quality_judgement"},
                memory_candidates=[
                    {
                        "memory_type": "task_episode",
                        "source_agent": "quality_judgement",
                        "source_trace_id": "trace-req-1",
                        "scope": {"org_id": "org-1"},
                        "content": {"summary": "quality summary"},
                        "confidence": 0.9,
                    }
                ],
            )

    monkeypatch.setattr("agent.graphs.memory_manager.nodes.ChildAgentRegistry", lambda: FakeRegistry())

    result = await MemoryManagerGraph().run(
        NormalizedRequest(
            request_id="req-1",
            workflow_run_id="wf-1",
            org_id="org-1",
            user_id="user-1",
            query="请判断质量",
        )
    )

    assert result["final_result"]["status"] == "completed"
    assert result["agent_output"]["answer"] == "quality answer"
    assert result["route_decision"]["selected_subgraph"] == "quality_judgement"


@pytest.mark.asyncio
async def test_memory_manager_run_triggers_governance_for_rejected_memory(monkeypatch):
    class FakeRegistry:
        async def run(self, agent_key, request):
            return AgentOutput(
                answer="candidate without scope",
                summary="bad candidate",
                trace={"source_agent": "quality_judgement"},
                memory_candidates=[
                    {
                        "memory_type": "task_episode",
                        "source_agent": "quality_judgement",
                        "content": {"summary": "missing source and scope"},
                        "confidence": 0.2,
                    }
                ],
            )

    monkeypatch.setattr("agent.graphs.memory_manager.nodes.ChildAgentRegistry", lambda: FakeRegistry())

    result = await MemoryManagerGraph().run(
        NormalizedRequest(request_id="req-2", workflow_run_id="wf-2", org_id="org-1", query="污染测试")
    )

    assert result["final_result"]["status"] == "completed"
    assert result["final_result"]["evaluation"]["metrics"]["contamination_detection_rate"] == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
pytest tests/test_memory_manager_graph_runtime.py -q
```

Expected: FAIL because `MemoryManagerGraph.run()` does not exist or graph nodes do not produce the required result shape.

- [ ] **Step 3: Extend MemoryAgentState**

Modify `backend/agent/graphs/memory_manager/state.py`:

```python
from agent.contracts import AgentOutput, ExecutionPlan, NormalizedRequest, RouteDecision
```

Add these fields to `MemoryAgentState`:

```python
    request: NormalizedRequest
    route_decision: RouteDecision
    execution_plan: ExecutionPlan
    selected_agent_outputs: list[dict[str, Any]]
    final_agent_output: dict[str, Any]
```

- [ ] **Step 4: Add route signal helper and planning nodes**

Modify `backend/agent/graphs/memory_manager/nodes.py` imports:

```python
import re

from agent.contracts import (
    AgentOutput,
    AgentRequest,
    ExecutionPlan,
    ExecutionPlanStep,
    MemoryCandidate,
    ModelPolicy,
    NormalizedRequest,
    RouteDecision,
    RouteSignals,
)
from agent.graphs.memory_manager.policy import select_subgraph
from agent.graphs.memory_manager.registry import ChildAgentRegistry
from agent.llm.model_policy import default_model_policy
```

Add helper functions near the top:

```python
TASK_KEYWORD_PATTERN = re.compile(r"(创建|新建|发起|提交).{0,8}(任务|检测|质检)|task|inspection", re.I)
MARKET_PATTERN = re.compile(r"(市场|价格|销量|渠道|售后)", re.I)
OPINION_PATTERN = re.compile(r"(舆情|投诉|举报|新闻|社交|论坛|评论)", re.I)
TREND_PATTERN = re.compile(r"(趋势|态势|预测|推演|风险演化)", re.I)
SAMPLING_PATTERN = re.compile(r"(抽检|抽样|监督检查|采样计划)", re.I)
LAB_PATTERN = re.compile(r"(实验室|检测指标|检验报告|理化|微生物|成分)", re.I)


def _route_signals_from_request(request: NormalizedRequest) -> RouteSignals:
    attachment_types = [str(item.kind or item.content_type or item.name or "file") for item in request.attachments]
    suffixes = [
        str(item.name or "").rsplit(".", 1)[-1].lower()
        for item in request.attachments
        if "." in str(item.name or "")
    ]
    has_images = bool(request.image_urls) or any(
        str(item.kind or "").lower() == "image"
        or str(item.content_type or "").lower().startswith("image/")
        or suffix in {"png", "jpg", "jpeg", "webp", "gif"}
        for item, suffix in zip(request.attachments, suffixes or [""] * len(request.attachments))
    )
    has_file_attachments = bool(request.attachments)
    has_non_pdf_documents = any(suffix and suffix not in {"pdf", "png", "jpg", "jpeg", "webp", "gif"} for suffix in suffixes)
    return RouteSignals(
        attachment_types=attachment_types,
        has_non_pdf_documents=has_non_pdf_documents,
        has_images=has_images,
        has_task_keyword=bool(TASK_KEYWORD_PATTERN.search(request.query or "")),
        has_file_attachments=has_file_attachments,
        needs_external_knowledge=bool((request.ext or {}).get("selected_rag_space_id") or (request.ext or {}).get("selected_rag_space")),
        request_kind=request.request_kind,
        selected_rag_space_id=str((request.ext or {}).get("selected_rag_space_id") or "") or None,
    )


def _agent_keys_for_query(query: str, fallback: str) -> list[str]:
    keys: list[str] = []
    if MARKET_PATTERN.search(query):
        keys.append("market_monitor")
    if OPINION_PATTERN.search(query):
        keys.append("public_opinion")
    if TREND_PATTERN.search(query):
        keys.append("trend_evolution")
    if SAMPLING_PATTERN.search(query):
        keys.append("supervision_sampling")
    if LAB_PATTERN.search(query):
        keys.append("lab_detection")
    if "quality_judgement" not in keys:
        keys.append(fallback)
    return list(dict.fromkeys(keys))
```

- [ ] **Step 5: Replace request and memory intake behavior**

Modify `request_intake` in `backend/agent/graphs/memory_manager/nodes.py`:

```python
async def request_intake(state: MemoryAgentState) -> dict[str, Any]:
    request = state.get("request")
    if request is None:
        ctx = state.get("task_context", {})
        request = NormalizedRequest(
            request_id=str(ctx.get("request_id") or ctx.get("trace_id") or "memory-request"),
            workflow_run_id=str(ctx.get("workflow_run_id") or ctx.get("trace_id") or ""),
            org_id=str(ctx.get("org_id") or ""),
            user_id=ctx.get("user_id"),
            query=str(ctx.get("query") or ""),
            metadata=dict(ctx.get("metadata") or {}),
            ext=dict(ctx.get("ext") or {}),
        )
    ctx = {
        **dict(state.get("task_context") or {}),
        "request_id": request.request_id,
        "workflow_run_id": request.workflow_run_id or request.request_id,
        "trace_id": request.workflow_run_id or request.request_id,
        "org_id": request.org_id,
        "user_id": request.user_id,
        "query": request.query,
    }
    events = list(state.get("memory_events", []))
    events.append(_event("input.received", trace_id=ctx.get("trace_id"), payload={"request_kind": request.request_kind}))
    return {"request": request, "task_context": ctx, "memory_events": events}
```

Modify `memory_context_loader` to keep the existing fallback but always return a stable shape:

```python
    if not mc:
        mc = {"items": [], "warnings": [], "degraded": False}
```

- [ ] **Step 6: Add task understanding, planning, routing, invocation, aggregation nodes**

Append these functions to `backend/agent/graphs/memory_manager/nodes.py` before `candidate_memory_builder`:

```python
async def task_understanding(state: MemoryAgentState) -> dict[str, Any]:
    request = state["request"]
    signals = _route_signals_from_request(request)
    decision = select_subgraph(signals)
    agent_outputs = dict(state.get("agent_outputs") or {})
    agent_outputs["manager"] = {
        **dict(agent_outputs.get("manager") or {}),
        "decision": "understood",
        "route_signals": signals.model_dump(),
        "selected_subgraph": decision.selected_subgraph,
        "trace_id": (state.get("task_context") or {}).get("trace_id"),
    }
    return {"route_decision": decision, "agent_outputs": agent_outputs}


async def task_planner(state: MemoryAgentState) -> dict[str, Any]:
    request = state["request"]
    decision = state["route_decision"]
    agent_keys = _agent_keys_for_query(request.query or "", decision.selected_subgraph)
    steps = [
        ExecutionPlanStep(
            step_id=f"step-{index + 1}",
            agent_key=agent_key,
            reason=f"Route request to {agent_key}",
            model_policy=default_model_policy("vision" if agent_key in {"quality_judgement", "lab_detection"} and (request.image_urls or any(a.kind == "image" for a in request.attachments)) else "text"),
        )
        for index, agent_key in enumerate(agent_keys)
    ]
    return {
        "execution_plan": ExecutionPlan(
            steps=steps,
            parallelizable=False,
            reason=decision.reason or "MemoryManagerGraph sequential child-agent plan",
        )
    }


async def agent_router(state: MemoryAgentState) -> dict[str, Any]:
    plan = state["execution_plan"]
    agent_outputs = dict(state.get("agent_outputs") or {})
    agent_outputs["manager"] = {
        **dict(agent_outputs.get("manager") or {}),
        "decision": "route",
        "routed_agents": [step.agent_key for step in plan.steps],
    }
    return {"agent_outputs": agent_outputs}


def _agent_request_from_step(state: MemoryAgentState, step: ExecutionPlanStep) -> AgentRequest:
    request = state["request"]
    selected_rag_space = (request.ext or {}).get("selected_rag_space")
    return AgentRequest(
        request_id=request.request_id,
        workflow_run_id=request.workflow_run_id or request.request_id,
        parent_trace_id=(state.get("task_context") or {}).get("trace_id"),
        org_id=request.org_id,
        user_id=request.user_id,
        workspace=request.workspace,
        plan_tier=request.plan_tier,
        capabilities=list(request.capabilities),
        request_kind=request.request_kind,
        query=request.query,
        metadata={**dict(request.metadata), **dict(step.input_overrides.get("metadata") or {})},
        ext=dict(request.ext),
        attachments=list(request.attachments),
        image_urls=list(request.image_urls),
        product_id=request.product_id,
        spec_code=request.spec_code,
        selected_rag_space=selected_rag_space if isinstance(selected_rag_space, dict) else None,
        memory_context=dict(state.get("memory_context") or {}),
        route_hints=dict(request.route_hints),
        task_context=dict(state.get("task_context") or {}),
        model_policy=step.model_policy,
    )


async def subgraph_invoker(state: MemoryAgentState) -> dict[str, Any]:
    registry = ChildAgentRegistry()
    selected_outputs: list[dict[str, Any]] = []
    agent_outputs = dict(state.get("agent_outputs") or {})
    for step in state["execution_plan"].steps:
        child_request = _agent_request_from_step(state, step)
        output = await registry.run(step.agent_key, child_request)
        selected_outputs.append({"agent_key": step.agent_key, "output": output.model_dump()})
        agent_outputs[step.agent_key] = {
            "status": output.action_state or "completed",
            "summary": output.summary,
            "candidate_memories": list(output.memory_candidates or []),
            "trace": dict(output.trace or {}),
        }
    return {"selected_agent_outputs": selected_outputs, "agent_outputs": agent_outputs}


async def result_aggregator(state: MemoryAgentState) -> dict[str, Any]:
    selected_outputs = list(state.get("selected_agent_outputs") or [])
    if not selected_outputs:
        output = AgentOutput(
            message_type="assistant_text",
            answer="当前没有可用的子智能体输出。",
            summary="No child Agent output",
            warnings=["no_child_agent_output"],
        )
    else:
        primary = AgentOutput.model_validate(selected_outputs[-1]["output"])
        summaries = [
            str(item["output"].get("summary") or item["output"].get("answer") or "")
            for item in selected_outputs
            if item.get("output")
        ]
        output = primary.model_copy(
            update={
                "summary": primary.summary or "；".join(item for item in summaries if item),
                "trace": {
                    **dict(primary.trace or {}),
                    "routed_agents": [item["agent_key"] for item in selected_outputs],
                },
            }
        )
    return {"final_agent_output": output.model_dump()}
```

- [ ] **Step 7: Update candidate memory builder to read final child output**

At the start of `candidate_memory_builder`, add:

```python
    final_output = dict(state.get("final_agent_output") or {})
    for cand in list(final_output.get("memory_candidates") or []):
        mid = cand.get("memory_id") or f"mem_{uuid.uuid4().hex[:12]}"
        cand["memory_id"] = mid
        cand.setdefault("status", "candidate")
        cand.setdefault("source_agent", str((final_output.get("trace") or {}).get("source_agent") or "unknown"))
        structured.append(cand)
        events.append(_event("memory.candidate_created", memory_id=mid, trace_id=ctx.get("trace_id"), payload={"agent": cand.get("source_agent")}))
```

Keep the existing loop over `agent_outputs` after this new block.

- [ ] **Step 8: Update result synthesizer to include AgentOutput**

In `result_synthesizer`, include the final output:

```python
    final_agent_output = dict(state.get("final_agent_output") or {})
    final = {
        "status": "completed",
        "memory_sources_used": len(mc.get("items", [])),
        "evaluation": eval_result,
        "agent_summaries": [
            {"agent": name, "status": out.get("status")}
            for name, out in agent_outputs.items()
            if name != "manager"
        ],
        "agent_output": final_agent_output,
        "route_decision": state.get("route_decision").model_dump() if state.get("route_decision") else None,
        "trace_id": ctx.get("trace_id"),
    }
```

- [ ] **Step 9: Rewire graph topology and implement run**

Modify `backend/agent/graphs/memory_manager/graph.py` imports:

```python
from agent.contracts import AgentOutput, NormalizedRequest
```

Import new nodes:

```python
    agent_router,
    result_aggregator,
    subgraph_invoker,
    task_planner,
    task_understanding,
```

In `build_graph()`, add new nodes:

```python
    builder.add_node("task_understanding", task_understanding)
    builder.add_node("task_planner", task_planner)
    builder.add_node("agent_router", agent_router)
    builder.add_node("subgraph_invoker", subgraph_invoker)
    builder.add_node("result_aggregator", result_aggregator)
```

Replace the professional-agent fanout edges with:

```python
    builder.add_edge("request_intake", "memory_context_loader")
    builder.add_edge("memory_context_loader", "task_understanding")
    builder.add_edge("task_understanding", "task_planner")
    builder.add_edge("task_planner", "agent_router")
    builder.add_edge("agent_router", "subgraph_invoker")
    builder.add_edge("subgraph_invoker", "result_aggregator")
    builder.add_edge("result_aggregator", "candidate_memory_builder")
```

Keep:

```python
    builder.add_edge("candidate_memory_builder", "write_gate_node")
    builder.add_edge("write_gate_node", "contamination_monitor_node")
```

Update `MemoryManagerGraph`:

```python
class MemoryManagerGraph:
    """Unified parent graph for child-Agent orchestration and memory governance."""

    def __init__(self):
        self._builder = build_graph()
        self._compiled = self._builder.compile()

    async def run(self, request: NormalizedRequest) -> dict[str, Any]:
        state = await self._compiled.ainvoke(
            {
                "request": request,
                "task_context": {
                    "request_id": request.request_id,
                    "workflow_run_id": request.workflow_run_id or request.request_id,
                    "trace_id": request.workflow_run_id or request.request_id,
                    "org_id": request.org_id,
                    "user_id": request.user_id,
                    "query": request.query,
                },
                "agent_outputs": {},
                "structured_memory": [],
                "memory_events": [],
                "dependency_edges": [],
                "contamination_alerts": [],
            }
        )
        final_result = dict(state.get("final_result") or {})
        agent_output = AgentOutput.model_validate(final_result.get("agent_output") or state.get("final_agent_output") or {})
        route_decision = final_result.get("route_decision") or (
            state.get("route_decision").model_dump() if state.get("route_decision") else None
        )
        return {
            "final_result": final_result,
            "agent_output": agent_output.model_dump(),
            "route_decision": route_decision,
            "workflow_version": "memory_manager_v2",
            "raw_state": {
                "memory_events": state.get("memory_events", []),
                "contamination_alerts": state.get("contamination_alerts", []),
                "execution_plan": state.get("execution_plan").model_dump() if state.get("execution_plan") else None,
            },
        }

    def compile(self, checkpointer=None):
        return self._builder.compile(checkpointer=checkpointer)

    @property
    def builder(self) -> StateGraph:
        return self._builder
```

- [ ] **Step 10: Run parent graph tests**

Run:

```bash
cd backend
pytest tests/test_memory_manager_graph_runtime.py -q
```

Expected: PASS.

- [ ] **Step 11: Run orchestrator smoke test**

Run:

```bash
cd backend
pytest tests/test_quality_agent_orchestrator_service.py -q
```

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add backend/agent/graphs/memory_manager backend/tests/test_memory_manager_graph_runtime.py backend/tests/test_quality_agent_orchestrator_service.py
git commit -m "feat: implement memory manager parent graph runtime"
```

---

## Task 6: Orchestrator Response Contract

**Files:**
- Modify: `backend/app/services/quality_agent_orchestrator_service.py`
- Test: `backend/tests/test_quality_agent_orchestrator_service.py`

- [ ] **Step 1: Add failing service test for graph response model validation**

Append to `backend/tests/test_quality_agent_orchestrator_service.py`:

```python
@pytest.mark.asyncio
async def test_run_chat_accepts_memory_manager_response(monkeypatch):
    persisted: list[AgentOutput] = []

    class FakeGraph:
        async def run(self, request):
            return {
                "final_result": {"status": "completed"},
                "agent_output": AgentOutput(answer="hello", summary="ok").model_dump(),
                "route_decision": None,
                "workflow_version": "memory_manager_v2",
            }

    async def fake_persist(self, request, output):
        persisted.append(output)
        return True

    async def fake_metrics(self, *args, **kwargs):
        return None

    monkeypatch.setattr(orchestrator_mod, "MemoryManagerGraph", lambda: FakeGraph())
    monkeypatch.setattr(QualityAgentOrchestratorService, "_persist_chat_result", fake_persist)
    monkeypatch.setattr(QualityAgentOrchestratorService, "_record_runtime_metrics", fake_metrics)

    result = await QualityAgentOrchestratorService().run_chat(
        {
            "request_id": "req-1",
            "workflow_run_id": "wf-1",
            "session_id": "session-1",
            "assistant_message_id": "assistant-1",
            "org_id": "org-1",
            "user_id": "user-1",
            "query": "hello",
        }
    )

    assert result["workflow_version"] == "memory_manager_v2"
    assert persisted[0].answer == "hello"
```

- [ ] **Step 2: Run test to verify current behavior**

Run:

```bash
cd backend
pytest tests/test_quality_agent_orchestrator_service.py::test_run_chat_accepts_memory_manager_response -q
```

Expected: PASS if Task 5 already preserves the expected response shape. If it fails with a `KeyError` or model validation error, continue with Step 3.

- [ ] **Step 3: Harden graph response validation**

In `backend/app/services/quality_agent_orchestrator_service.py`, replace:

```python
        agent_output = AgentOutput.model_validate(result["agent_output"])
```

with:

```python
        result_agent_output = result.get("agent_output") or (result.get("final_result") or {}).get("agent_output") or {}
        agent_output = AgentOutput.model_validate(result_agent_output)
```

Keep the existing route metrics logic:

```python
        route_decision = agent_output.route_decision
```

- [ ] **Step 4: Run orchestrator tests**

Run:

```bash
cd backend
pytest tests/test_quality_agent_orchestrator_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/quality_agent_orchestrator_service.py backend/tests/test_quality_agent_orchestrator_service.py
git commit -m "fix: harden orchestrator graph response handling"
```

---

## Task 7: Topology Catalog Alignment

**Files:**
- Modify: `backend/agent/topology_catalog.py`
- Test: `backend/tests/test_agent_ops_api.py`

- [ ] **Step 1: Add failing topology assertions**

Modify `backend/tests/test_agent_ops_api.py` in the topology test section. Add:

```python
def test_topology_catalog_includes_parent_and_child_agents():
    from agent.topology_catalog import get_registered_subgraphs, get_topology

    registered = {item["subgraph_key"]: item for item in get_registered_subgraphs()}
    assert set(registered) >= {
        "quality_judgement",
        "market_monitor",
        "public_opinion",
        "trend_evolution",
        "supervision_sampling",
        "lab_detection",
        "governance_recovery",
    }
    assert all(item["entry_graph"] == "MemoryManagerGraph" for item in registered.values())

    topology = get_topology("all", include_root=True)
    edge_pairs = {(edge["source"], edge["target"]) for edge in topology["edges"]}
    assert ("agent_router", "quality_judgement") in edge_pairs
    assert ("agent_router", "market_monitor") in edge_pairs
    assert ("contamination_monitor_node", "governance_recovery") in edge_pairs
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_agent_ops_api.py::test_topology_catalog_includes_parent_and_child_agents -q
```

Expected: FAIL because current topology does not expose the new parent-child edges.

- [ ] **Step 3: Update registered subgraphs**

In `backend/agent/topology_catalog.py`, ensure `REGISTERED_SUBGRAPHS` includes:

```python
{
    "name": "Governance Recovery",
    "description": "Memory contamination provenance, propagation, rollback, recovery, and replay evaluation.",
    "workflow_binding": "governance_recovery_v1",
    "subgraph_key": "governance_recovery",
    "entry_graph": "MemoryManagerGraph",
    "supports_start_stop": False,
    "graph_version": "v1",
    "is_active": True,
}
```

Keep `quality_judgement` active. Set planned business Agents to inactive until Task 3 skeletons are present:

```python
"is_active": False
```

for `market_monitor`, `public_opinion`, `trend_evolution`, `supervision_sampling`, and `lab_detection`.

- [ ] **Step 4: Update root topology nodes and edges**

Set `ROOT_NODES`:

```python
ROOT_NODES = [
    {"id": "request_intake", "label": "Request Intake", "kind": "root"},
    {"id": "memory_context_loader", "label": "Memory Context Loader", "kind": "root"},
    {"id": "task_understanding", "label": "Task Understanding", "kind": "root"},
    {"id": "task_planner", "label": "Task Planner", "kind": "root"},
    {"id": "agent_router", "label": "Agent Router", "kind": "root"},
    {"id": "result_aggregator", "label": "Result Aggregator", "kind": "root"},
    {"id": "candidate_memory_builder", "label": "Candidate Memory Builder", "kind": "memory"},
    {"id": "write_gate_node", "label": "Write Gate", "kind": "memory"},
    {"id": "contamination_monitor_node", "label": "Contamination Monitor", "kind": "memory"},
    {"id": "result_synthesizer", "label": "Result Synthesizer", "kind": "root"},
]
```

Set `ROOT_EDGES`:

```python
ROOT_EDGES = [
    {"source": "request_intake", "target": "memory_context_loader"},
    {"source": "memory_context_loader", "target": "task_understanding"},
    {"source": "task_understanding", "target": "task_planner"},
    {"source": "task_planner", "target": "agent_router"},
    {"source": "agent_router", "target": "result_aggregator"},
    {"source": "result_aggregator", "target": "candidate_memory_builder"},
    {"source": "candidate_memory_builder", "target": "write_gate_node"},
    {"source": "write_gate_node", "target": "contamination_monitor_node"},
    {"source": "contamination_monitor_node", "target": "result_synthesizer"},
    {"source": "contamination_monitor_node", "target": "governance_recovery"},
    {"source": "governance_recovery", "target": "result_synthesizer"},
]
```

- [ ] **Step 5: Add child Agent edge wiring in `get_topology()`**

Inside `get_topology()`, when `include_root` is true and a selected key is a registered child Agent, append:

```python
edges.append({"source": "agent_router", "target": key})
edges.append({"source": key, "target": "result_aggregator"})
```

Do not add `{"source": key, "target": "result_aggregator"}` for `governance_recovery`; governance already routes from `contamination_monitor_node`.

- [ ] **Step 6: Run topology tests**

Run:

```bash
cd backend
pytest tests/test_agent_ops_api.py::test_topology_catalog_includes_parent_and_child_agents -q
```

Expected: PASS.

- [ ] **Step 7: Run Agent Ops tests**

Run:

```bash
cd backend
pytest tests/test_agent_ops_api.py -q
```

Expected: PASS. If existing assertions expect only `quality_judgement`, update them to include the newly registered child Agents while preserving `quality_judgement` as default target.

- [ ] **Step 8: Commit**

```bash
git add backend/agent/topology_catalog.py backend/tests/test_agent_ops_api.py
git commit -m "feat: align agent topology with parent graph"
```

---

## Task 8: Memory Candidate Gate And Governance Verification

**Files:**
- Modify: `backend/agent/graphs/memory_manager/nodes.py`
- Test: `backend/tests/test_memory_manager_graph_runtime.py`

- [ ] **Step 1: Add tests for candidate approval and rejection**

Append to `backend/tests/test_memory_manager_graph_runtime.py`:

```python
@pytest.mark.asyncio
async def test_memory_candidate_with_source_and_scope_becomes_active(monkeypatch):
    class FakeRegistry:
        async def run(self, agent_key, request):
            return AgentOutput(
                answer="ok",
                summary="candidate ok",
                trace={"source_agent": "quality_judgement"},
                memory_candidates=[
                    {
                        "memory_type": "task_episode",
                        "source_agent": "quality_judgement",
                        "source_trace_id": "trace-ok",
                        "scope": {"org_id": "org-1", "task_id": "task-1"},
                        "content": {"summary": "usable memory"},
                        "confidence": 0.88,
                    }
                ],
            )

    monkeypatch.setattr("agent.graphs.memory_manager.nodes.ChildAgentRegistry", lambda: FakeRegistry())

    result = await MemoryManagerGraph().run(
        NormalizedRequest(request_id="req-ok", workflow_run_id="wf-ok", org_id="org-1", query="质量")
    )

    events = result["raw_state"]["memory_events"]
    assert any(event["event_type"] == "memory.write_created" for event in events)
    assert result["raw_state"]["contamination_alerts"] == []


@pytest.mark.asyncio
async def test_memory_candidate_without_scope_is_rejected(monkeypatch):
    class FakeRegistry:
        async def run(self, agent_key, request):
            return AgentOutput(
                answer="bad",
                summary="candidate bad",
                trace={"source_agent": "quality_judgement"},
                memory_candidates=[
                    {
                        "memory_type": "task_episode",
                        "source_agent": "quality_judgement",
                        "source_trace_id": "trace-bad",
                        "content": {"summary": "missing scope"},
                        "confidence": 0.88,
                    }
                ],
            )

    monkeypatch.setattr("agent.graphs.memory_manager.nodes.ChildAgentRegistry", lambda: FakeRegistry())

    result = await MemoryManagerGraph().run(
        NormalizedRequest(request_id="req-bad", workflow_run_id="wf-bad", org_id="org-1", query="质量")
    )

    assert any(alert["alert_type"] == "conflict" for alert in result["raw_state"]["contamination_alerts"])
```

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
pytest tests/test_memory_manager_graph_runtime.py::test_memory_candidate_with_source_and_scope_becomes_active tests/test_memory_manager_graph_runtime.py::test_memory_candidate_without_scope_is_rejected -q
```

Expected: PASS if Task 5 candidate integration is correct. If not, continue with Step 3.

- [ ] **Step 3: Harden write gate scope and source checks**

In `write_gate_node`, replace:

```python
            has_source = bool(item.get("source") or item.get("trace_id"))
```

with:

```python
            has_source = bool(
                item.get("source")
                or item.get("trace_id")
                or item.get("source_trace_id")
                or item.get("source_agent")
            )
```

Replace:

```python
            has_scope = bool(
                item.get("scope")
                or item.get("task_id")
                or ctx.get("task_id")
            )
```

with:

```python
            scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
            has_scope = bool(scope or item.get("task_id") or ctx.get("task_id"))
```

- [ ] **Step 4: Run memory runtime tests**

Run:

```bash
cd backend
pytest tests/test_memory_manager_graph_runtime.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/graphs/memory_manager/nodes.py backend/tests/test_memory_manager_graph_runtime.py
git commit -m "test: verify memory candidate gate and governance branch"
```

---

## Task 9: Legacy InspectionGraph Absorption Guardrails

**Files:**
- Modify: `backend/app/services/inspection_pipeline_service.py`
- Test: `backend/tests/test_inspection_pipeline_service.py`
- Test: `backend/tests/test_governance_logic.py`

- [ ] **Step 1: Add a module-level deprecation note**

At the top of `backend/agent/graph/inspection_graph.py`, under imports, add:

```python
# Transitional pipeline: production orchestration should move through
# MemoryManagerGraph -> QualityJudgementAgent/LabDetectionAgent. This class is
# kept until inspection_pipeline_service is migrated without breaking existing
# task execution tests.
```

- [ ] **Step 2: Add test asserting old graph remains isolated from parent orchestration**

Append to `backend/tests/test_governance_logic.py`:

```python
def test_inspection_graph_is_transitional_pipeline():
    graph = InspectionGraph()
    assert hasattr(graph, "run")
    assert not hasattr(graph, "builder")
```

- [ ] **Step 3: Add migration marker to inspection pipeline service**

In `backend/app/services/inspection_pipeline_service.py`, near the `InspectionGraph()` construction, add a short comment:

```python
            # Transitional path: keep existing task execution stable while the
            # parent graph runtime adopts QualityJudgementAgent and LabDetectionAgent.
```

Do not change behavior in this task.

- [ ] **Step 4: Run related tests**

Run:

```bash
cd backend
pytest tests/test_governance_logic.py::test_inspection_graph_is_transitional_pipeline tests/test_inspection_pipeline_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/graph/inspection_graph.py backend/app/services/inspection_pipeline_service.py backend/tests/test_governance_logic.py
git commit -m "docs: mark inspection graph as transitional"
```

---

## Task 10: End-To-End Verification

**Files:**
- No source changes expected.
- Test commands only.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd backend
pytest \
  tests/test_agent_runtime_contracts.py \
  tests/test_model_policy.py \
  tests/test_child_agent_skeletons.py \
  tests/test_memory_manager_graph_runtime.py \
  tests/test_quality_agent_orchestrator_service.py \
  tests/test_quality_agent_routing.py \
  tests/test_quality_judgement.py \
  tests/test_chat_flow.py \
  tests/test_agent_ops_api.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run full backend test suite**

Run:

```bash
cd backend
pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run import smoke checks**

Run:

```bash
cd backend
python -c "from agent.graphs.memory_manager import MemoryManagerGraph; from agent.subgraphs import QualityJudgementSubgraph, MarketMonitorAgent, GovernanceRecoveryAgent; print('OK')"
```

Expected:

```text
OK
```

- [ ] **Step 4: Scan for hardcoded secrets**

Run:

```bash
rg -n "api_key\\s*=\\s*['\\\"][A-Za-z0-9_-]{20,}|DEEPSEEK_API_KEY\\s*=\\s*[A-Za-z0-9_-]{20,}|VOLCENGINE_API_KEY\\s*=\\s*[A-Za-z0-9_-]{20,}" backend docs --glob '!runtime_uploads/**'
```

Expected: no hardcoded live keys in backend code or docs.

- [ ] **Step 5: Inspect final graph shape**

Run:

```bash
cd backend
python -c "from agent.topology_catalog import get_topology; topology = get_topology('all', include_root=True); print(len(topology['nodes']), len(topology['edges'])); print(sorted({edge['source'] for edge in topology['edges'] if edge['source'] == 'agent_router'}))"
```

Expected: the command prints nonzero node/edge counts and includes `agent_router` as a routing source.

- [ ] **Step 6: Confirm verification task did not create source changes**

Run:

```bash
git status --short
```

Expected: no source changes from this verification task. If files changed unexpectedly, inspect them and either revert generated artifacts or create a follow-up plan task with exact file ownership.

---

## Self-Review Checklist

- Spec coverage:
  - Parent graph runtime: Task 5.
  - Child Agent uniform contracts: Tasks 1, 3, 4.
  - QualityJudgementAgent first integration: Task 4 and Task 5.
  - Professional Agent skeletons: Task 3.
  - Model policy and DeepSeek/environment configuration: Task 2.
  - Memory gating and governance recovery: Task 5 and Task 8.
  - Topology and Agent Ops alignment: Task 7.
  - Legacy `InspectionGraph` transition decision: Task 9.
  - Verification and secret scan: Task 10.
- Placeholder scan: no task contains missing acceptance criteria or deferred implementation language.
- Type consistency:
  - `AgentRequest`, `ExecutionPlan`, `ExecutionPlanStep`, `MemoryCandidate`, and `ModelPolicy` are introduced in Task 1 and reused consistently.
  - `AgentOutput.memory_candidates`, `warnings`, `model_usage`, and `trace` are added before any runtime task uses them.
  - `MemoryManagerGraph.run()` returns `agent_output`, `final_result`, `route_decision`, `workflow_version`, and `raw_state`, matching orchestrator usage.
