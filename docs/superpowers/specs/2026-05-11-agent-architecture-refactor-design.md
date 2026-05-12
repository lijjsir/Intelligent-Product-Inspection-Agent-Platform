# Agent Architecture Refactor Design

**Date**: 2026-05-11
**Status**: Approved
**Source Docs**: PIAP_AGENT_FUNCTION_v1_0_0, PIAP_ROLE_v1_0_0, PIAP_FRONT_BACKEND_UNIFIED_DETAILED_DESIGN_v1_0_0

## 1. Summary

Restructure the agent graph topology from a fragmented 3-quality-graph + separate-memory-graph layout into a unified parent-graph architecture aligned with the PIAP design documents:

- Rename `shared_memory_hierarchy` → `memory_manager` (MemoryManagerAgent)
- Merge `legacy_quality` + `llm_native_quality` → `quality_judgement` (QualityJudgementAgent)
- Keep `quality_chat` as a standalone subgraph
- Remove `quality_root` parent graph (routing absorbed by MemoryManagerAgent)
- Retain 5 planned professional agent stubs as placeholders

## 2. Target Architecture

```
MemoryManagerAgent (唯一父图)
├── request_intake          → 请求标准化 + 意图识别
├── memory_context_loader   → 加载共享记忆上下文
├── manager_route_policy    → 按意图/文件类型/风险路由到子图
├── [子图执行层]
│   ├── QualityJudgementAgent  ← 合并 Legacy + LLM-native
│   ├── QualityChatGraph      ← 保留，独立对话入口
│   ├── MarketMonitorAgent    (stub · 规划中)
│   ├── PublicOpinionAgent    (stub · 规划中)
│   ├── TrendEvolutionAgent   (stub · 规划中)
│   ├── SupervisionSamplingAgent (stub · 规划中)
│   └── LabDetectionAgent     (stub · 规划中)
├── [记忆生命周期]
│   ├── candidate_memory_builder → 候选记忆生成
│   ├── write_gate_node         → 写入门控
│   └── contamination_monitor   → 污染监控
├── [治理恢复]
│   ├── provenance_node          → 来源追踪
│   ├── propagation_graph_node   → 传播分析
│   ├── rollback_planner_node    → 回滚计划
│   ├── governance_recovery_agent → 恢复执行
│   └── replay_evaluation_node   → 恢复验证
└── result_synthesizer        → 聚合输出 + 冲突协调
```

## 3. File Changes

### 3.1 Rename

| Old | New | Notes |
|-----|-----|-------|
| `agent/subgraphs/shared_memory_hierarchy/` | `agent/graphs/memory_manager/` | Move from subgraphs to graphs (parent role) |
| Class `SharedMemoryHierarchyGraph` | `MemoryManagerGraph` | |
| All internal imports of `shared_memory_hierarchy` | `memory_manager` | |

### 3.2 Merge

| Old | New | Notes |
|-----|-----|-------|
| `agent/subgraphs/legacy_quality/` | `agent/subgraphs/quality_judgement/` | Legacy nodes merged in |
| `agent/subgraphs/llm_native_quality/` | *(deleted)* | Nodes merged into quality_judgement |
| `agent/subgraphs/llm_native_quality/product_adapters.py` | `agent/subgraphs/quality_judgement/product_adapters.py` | Keep all field mappings (screw/food/electronics) unchanged |
| Class `LegacyQualitySubgraph` | `QualityJudgementSubgraph` | |
| Class `LLMNativeQualitySubgraph` | *(deleted)* | |

QualityJudgementAgent internal node mapping:

```
intake_normalizer        ← llm_native_quality.intake_normalizer
file_loader              ← llm_native_quality.file_loader
contract_inferencer      ← llm_native_quality.contract_inferencer_dspy
planner                  ← merged: legacy.planner + native.planner
task_extractor           ← legacy_quality.task_extractor
knowledge_router         ← merged: legacy.knowledge + native.knowledge_router
tool_loop                ← llm_native_quality.tool_loop
reasoning                ← merged: legacy.reasoning + native evidence logic
evidence_synthesizer     ← llm_native_quality.evidence_synthesizer
review_gate              ← merged: legacy.quality_gate + native.review_gate
task_executor            ← legacy_quality.task_executor
persist_emit             ← merged: legacy.finalizer + native.persist_emit
```

Internal routing: the merged graph uses conditional edges based on RouteSignals (same signals that quality_root previously used). When `has_task_keyword=true` or the request needs structured task creation, the legacy path (task_extractor → reasoning → task_executor) is preferred. When file attachments or non-PDF documents are present, the native path (contract_inferencer → tool_loop → evidence_synthesizer) is preferred. Common nodes (planner, knowledge_router, review_gate, persist_emit) are shared.

### 3.3 Delete

| Path | Reason |
|------|--------|
| `agent/graphs/quality_root/` | Routing logic absorbed by MemoryManagerAgent |

### 3.4 Keep Unchanged

| Path | Notes |
|------|-------|
| `agent/subgraphs/quality_chat/` | Independent chat entry, unchanged |
| `agent/contracts/` | Contracts remain valid with minor updates |
| `agent/llm/` | LLM gateway, unchanged |
| `agent/rag/` | RAG pipeline, unchanged |
| `agent/stability/` | Stability analysis, unchanged |
| `agent/tools/` | Tool registry, update references |

### 3.5 Update

| Path | Change |
|------|--------|
| `agent/topology_catalog.py` | Rewrite REGISTERED_SUBGRAPHS and all node/edge definitions |
| `backend/app/services/quality_agent_orchestrator_service.py` | Update graph references |
| `backend/tests/test_llm_native_quality.py` | Update imports |

## 4. Data Flow

```
User Request (chat / task / file upload)
  → API Layer (FastAPI /v1/agent/...)
  → QualityAgentOrchestratorService
  → MemoryManagerAgent.run(request)
    → request_intake: NormalizedRequest
    → memory_context_loader: load from MemoryService
    → manager_route_policy: select target subgraph
    → [condition] → QualityJudgementAgent / QualityChatGraph / (stub agents)
    → candidate_memory_builder: extract reusable context
    → write_gate_node: validate & persist memory
    → contamination_monitor: check for bad memory
    → [if contamination] → governance loop
    → result_synthesizer: aggregate outputs
  → ResponseEnvelope to frontend
```

## 5. Model Configuration

| Use Case | Provider | Model | API Key Source |
|----------|----------|-------|----------------|
| Agent reasoning (chat, planner, reasoning, gate) | DeepSeek | V4 Flash | Settings (env: `DEEPSEEK_API_KEY`) |
| Vision tasks (defect detection, image analysis) | Volcengine Ark | Existing vision model | Settings (env: `VOLCENGINE_API_KEY`) |
| Embedding / RAG | Volcengine | Existing embed model | Settings (env: `VOLCENGINE_API_KEY`) |

API key `16DB5F7B-26AF-4EBF-B13A-DA3155362D97` must be stored as an environment variable (`DEEPSEEK_API_KEY`), not hardcoded.

### 5.1 LLMClient Multi-Provider Support

The `LLMClient` currently hardcodes Volcengine Ark as the sole provider. It must be updated to support provider selection:

- Add `provider` parameter to `__init__` (default `"volcengine"`)
- When `provider="deepseek"`: use DeepSeek API base URL and API key from settings
- When `provider="volcengine"`: existing Volcengine Ark logic unchanged
- The `ModelSelector` and `AgentOrchestratorService` instantiate separate clients per use case:
  - `LLMClient(provider="deepseek", ...)` for agent reasoning nodes
  - `LLMClient(provider="volcengine", model_id=<vision_model>)` for vision nodes
- Add to `backend/app/core/config.py`:
  ```python
  DEEPSEEK_API_KEY: str = ""
  DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
  DEEPSEEK_MODEL_ID: str = "deepseek-v4-flash"
  ```

## 6. Topology Catalog Changes

REGISTERED_SUBGRAPHS after refactor:

```python
REGISTERED_SUBGRAPHS = [
    {
        "name": "Quality Judgement",
        "description": "统一质量判定（合并 Legacy + LLM-native），支持 chat / file / task 多策略。",
        "subgraph_key": "quality_judgement",
        "entry_graph": "MemoryManagerGraph",
        "graph_version": "v2",
        "is_active": True,
    },
    {
        "name": "Quality Chat",
        "description": "轻量级智能问答入口，支持附件上传和 RAG 空间选择。",
        "subgraph_key": "quality_chat",
        "entry_graph": "MemoryManagerGraph",
        "graph_version": "v1",
        "is_active": True,
    },
    {
        "name": "Market Monitor",
        "description": "市场价格、销量、渠道异常检测（规划中）。",
        "subgraph_key": "market_monitor",
        "entry_graph": "MemoryManagerGraph",
        "graph_version": "v0",
        "is_active": False,
    },
    # ... similar for public_opinion, trend_evolution, supervision_sampling, lab_detection
]
```

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Merging Legacy + Native may break existing task flows | Keep both strategy paths as internal branches; route by request signals |
| MemoryManagerAgent takes over routing → single point of failure | agent_ops health check monitors graph execution; fallback to direct QualityJudgementAgent call |
| product_adapters.py (screw/food/electronics) must work post-merge | Move adapters into quality_judgement/adapters/, keep all field mappings unchanged |
| API keys in code are a security risk | All keys go through settings/env vars; the DeepSeek key is placed in .env (gitignored) |

## 8. Out of Scope

- Implementing real MarketMonitorAgent, PublicOpinionAgent, TrendEvolutionAgent, SupervisionSamplingAgent, LabDetectionAgent (stubs only)
- Frontend workspace restructuring (app/ops/governance) — separate project
- Database schema changes for new memory governance tables
- Role/capability system overhaul
