# Tool Management Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tool management phase 1 genuinely usable in development with real backend data, real tool testing, real execution monitoring, and no misleading preview-only success paths.

**Architecture:** Keep the current `tool_registry + tool_executions` MVP model, strengthen repository/service/API behavior, then align the frontend to those real semantics. Remove or downgrade second/third-phase fake interactions instead of pretending versioning, bindings, import pipelines, and realtime streams are already complete.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, pytest, Vue 3, Pinia, Vue Router, Element Plus, TypeScript, Vite.

---

## File Structure

### Backend core

- `backend/app/models/tool.py`
  Responsibility: current tool definition and execution log ORM model.
- `backend/app/schemas/tool.py`
  Responsibility: request/response contracts for list/detail/test/execution APIs.
- `backend/app/repositories/tool_repo.py`
  Responsibility: database queries for tools and executions.
- `backend/app/services/tool_service.py`
  Responsibility: phase-1 business logic for tool overview, detail, edit, test, execution monitoring.
- `backend/app/services/tool_sync_service.py`
  Responsibility: builtin tool manifest scanning and sync to database.
- `backend/app/api/v1/tools.py`
  Responsibility: expose only real phase-1 API behavior and honestly downgrade unfinished phase-2/3 endpoints.
- `backend/agent/tools/resolver.py`
  Responsibility: keep MVP runtime behavior, but document and expose it honestly.

### Frontend core

- `frontend/src/types/tools.types.ts`
  Responsibility: phase-1 UI types aligned with real backend payloads.
- `frontend/src/api/tools.api.ts`
  Responsibility: call real phase-1 backend endpoints by default.
- `frontend/src/stores/tools.store.ts`
  Responsibility: state management for overview, tools, detail, testing, executions.
- `frontend/src/router/routes/ops.routes.ts`
  Responsibility: route/menu exposure for real and deferred tool pages.
- `frontend/src/composables/useMenu.ts`
  Responsibility: left-menu entries for tool pages.
- `frontend/src/views/ops/tools/ToolOverviewView.vue`
  Responsibility: phase-1 tool dashboard.
- `frontend/src/views/ops/tools/ToolCatalogView.vue`
  Responsibility: phase-1 tool browser, search, filter, create, disable, lightweight test.
- `frontend/src/views/ops/tools/ToolDetailView.vue`
  Responsibility: phase-1 detail with overview/config/schema/test/executions only.
- `frontend/src/views/ops/tools/ToolExecutionView.vue`
  Responsibility: phase-1 global execution monitoring.
- `frontend/src/views/ops/tools/ToolImportView.vue`
  Responsibility: honest phase-3 placeholder with builtin sync only.
- `frontend/src/views/ops/tools/ToolBindingView.vue`
  Responsibility: honest phase-2 placeholder or disabled entry.

### Verification and docs

- `backend/tests/test_tools_api.py`
  Responsibility: API/service contract coverage for phase-1 endpoints.
- `docs/tool_management.md`
  Responsibility: reflect actual phase-1 delivery and defer phase-2/3 accurately.

---

### Task 1: Tighten Tool Schemas And Repository Queries

**Files:**
- Modify: `backend/app/schemas/tool.py`
- Modify: `backend/app/repositories/tool_repo.py`
- Test: `backend/tests/test_tools_api.py`

- [ ] **Step 1: Write a failing backend test for execution filtering semantics**

```python
@pytest.mark.asyncio
async def test_list_executions_filters_execution_type_and_agent(monkeypatch):
    class FakeToolService:
        def __init__(self, db, org_id):
            self.db = db
            self.org_id = org_id

        async def list_executions(self, payload):
            assert payload["execution_type"] == "test"
            assert payload["agent_id"] == "agent-1"
            return {"items": [], "total": 0, "page": 1, "size": 20}

    monkeypatch.setattr(tools_api, "ToolService", FakeToolService)

    response = await tools_api.list_executions(
        page=1,
        size=20,
        agent_id="agent-1",
        execution_type="test",
        status_filter=None,
        current=current_user(),
        db=object(),
    )

    assert response.data.total == 0
```

- [ ] **Step 2: Run the focused backend test and verify RED**

Run:

```bash
pytest backend/tests/test_tools_api.py -k execution_type -q
```

Expected: FAIL if the test has not been added yet, or FAIL for missing/incorrect filtering behavior.

- [ ] **Step 3: Update execution query/request schema to match phase-1 filters**

```python
class ToolExecutionListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=200)
    tool_id: str | None = None
    agent_id: str | None = None
    status: str | None = None
    execution_type: str | None = None
```

Also ensure `ToolExecutionResponse` only exposes fields phase 1 can fill truthfully.

- [ ] **Step 4: Push tool/execution filtering into repository queries**

```python
async def list_executions(
    self,
    org_id: str,
    *,
    tool_id: str | None = None,
    agent_id: str | None = None,
    status: str | None = None,
    execution_type: str | None = None,
    page: int = 1,
    size: int = 20,
) -> list[ToolExecution]:
    stmt = select(ToolExecution).where(ToolExecution.org_id == org_id)
    if tool_id:
        stmt = stmt.where(ToolExecution.tool_id == tool_id)
    if agent_id:
        stmt = stmt.where(ToolExecution.agent_id == agent_id)
    if status:
        stmt = stmt.where(ToolExecution.status == status)
    if execution_type:
        stmt = stmt.where(ToolExecution.execution_type == execution_type)
    stmt = stmt.order_by(ToolExecution.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await self._session.execute(stmt)
    return list(result.scalars().all())
```

```python
async def count_executions(
    self,
    org_id: str,
    *,
    tool_id: str | None = None,
    agent_id: str | None = None,
    status: str | None = None,
    execution_type: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(ToolExecution).where(ToolExecution.org_id == org_id)
    if tool_id:
        stmt = stmt.where(ToolExecution.tool_id == tool_id)
    if agent_id:
        stmt = stmt.where(ToolExecution.agent_id == agent_id)
    if status:
        stmt = stmt.where(ToolExecution.status == status)
    if execution_type:
        stmt = stmt.where(ToolExecution.execution_type == execution_type)
    result = await self._session.execute(stmt)
    return int(result.scalar_one())
```

- [ ] **Step 5: Fix global/builtin visibility in active tool queries**

```python
async def list_active(self, org_id: str) -> list[ToolRegistry]:
    result = await self._session.execute(
        select(ToolRegistry)
        .where(
            or_(ToolRegistry.org_id == org_id, ToolRegistry.org_id.is_(None)),
            ToolRegistry.is_active.is_(True),
            ToolRegistry.status == "active",
        )
        .order_by(ToolRegistry.updated_at.desc(), ToolRegistry.display_name.asc())
    )
    return list(result.scalars().all())
```

- [ ] **Step 6: Run the targeted backend tests and verify GREEN**

Run:

```bash
pytest backend/tests/test_tools_api.py -q
```

Expected: PASS for schema/API contract tests touching execution filters.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/tool.py backend/app/repositories/tool_repo.py backend/tests/test_tools_api.py
git commit -m "feat: tighten tool execution query contracts for phase 1"
```

---

### Task 2: Make ToolService Phase-1 Truthful

**Files:**
- Modify: `backend/app/services/tool_service.py`
- Modify: `backend/app/models/tool.py`
- Test: `backend/tests/test_tools_api.py`

- [ ] **Step 1: Write a failing backend test for real phase-1 detail shape**

```python
@pytest.mark.asyncio
async def test_get_tool_detail_returns_phase1_real_tabs_only(monkeypatch):
    class FakeToolService:
        def __init__(self, db, org_id):
            pass

        async def get_tool_detail(self, tool_id):
            return {
                "id": tool_id,
                "tool_key": "rag.standard_search",
                "display_name": "标准知识库检索",
                "description": "desc",
                "category": "RAG",
                "tool_type": "rag",
                "status": "active",
                "risk_level": "low",
                "is_readonly": True,
                "source_type": "builtin",
                "health_status": "healthy",
                "active_version": "1.0.0",
                "bound_agent_names": [],
                "today_calls": 3,
                "success_rate": 1.0,
                "avg_latency_ms": 20,
                "active_version_id": f"{tool_id}:1.0.0",
                "executions": [],
                "parameters_schema": {},
                "returns_schema": {},
                "timeout_ms": 30000,
                "rate_limit_rpm": 60,
            }

    monkeypatch.setattr(tools_api, "ToolService", FakeToolService)
    response = await tools_api.get_tool_detail("tool-1", current=current_user(), db=object())
    assert "executions" in response.data
    assert "bindings" not in response.data or response.data["bindings"] == []
```

- [ ] **Step 2: Run the focused backend test and verify RED**

Run:

```bash
pytest backend/tests/test_tools_api.py -k phase1_real_tabs_only -q
```

Expected: FAIL before service/schema cleanup.

- [ ] **Step 3: Remove fake phase-2/3 payloads from detail serialization**

```python
detail = self._serialize_tool(tool, summary)
detail["active_version_id"] = f"{tool.id}:{tool.version}"
detail["executions"] = [self._serialize_execution(item) for item in recent_executions]
detail["method"] = self._derive_method(tool)
detail["handler_path"] = self._derive_handler_path(tool)
detail["auth_type"] = "none" if not tool.endpoint else "bearer"
detail["secret_ref"] = None
detail["parameters_schema"] = tool.parameters_schema or {}
detail["returns_schema"] = tool.returns_schema or {}
detail["timeout_ms"] = tool.timeout_ms
detail["retry_policy"] = tool.retry_policy
detail["rate_limit_rpm"] = tool.rate_limit_rpm
```

Do not attach fake `versions`, fake `bindings`, or synthetic `audit_logs` as if they were phase-1 real entities.

- [ ] **Step 4: Align list/detail semantics around status vs health**

```python
def _serialize_tool(self, tool: ToolRegistry, summary: dict[str, Any]) -> dict[str, Any]:
    success_rate = summary.get("success_rate", 0.0)
    health = tool.health_status or "unknown"
    if tool.status == "active" and health == "unknown":
        calls = summary.get("total_calls", 0)
        if calls > 0:
            health = "healthy" if success_rate >= 0.95 else "degraded" if success_rate >= 0.7 else "unhealthy"
    return {
        "id": tool.id,
        "tool_key": tool.name,
        "display_name": tool.display_name,
        "description": tool.description,
        "category": tool.category or self._derive_category_fallback(tool),
        "tool_type": tool.tool_type or self._derive_type_fallback(tool),
        "status": tool.status or ("active" if tool.is_active else "disabled"),
        "risk_level": tool.risk_level or ("low" if tool.is_readonly else "medium"),
        "is_readonly": bool(tool.is_readonly),
        "source_type": tool.source_type or ("openapi" if tool.endpoint else "manual"),
        "health_status": health,
        "active_version": tool.version,
        "bound_agent_names": [],
        "today_calls": summary.get("total_calls", 0),
        "success_rate": success_rate,
        "avg_latency_ms": summary.get("avg_latency_ms", 0),
        "created_at": tool.created_at,
        "updated_at": tool.updated_at,
    }
```

- [ ] **Step 5: Make execution serialization honest for missing agent names**

```python
def _serialize_execution(self, item: ToolExecution) -> dict[str, Any]:
    return {
        "id": item.id,
        "tool_id": item.tool_id,
        "tool_name": item.tool_name,
        "agent_id": item.agent_id or "",
        "agent_name": item.agent_id or "未绑定",
        "task_id": item.task_id,
        "execution_type": item.execution_type or "runtime",
        "status": item.status,
        "duration_ms": int(item.latency_ms or 0),
        "input_summary": self._summarize_payload(item.input_redacted or item.input_payload),
        "output_summary": self._summarize_payload(item.output_redacted or item.output_payload),
        "error_message": item.error_message,
        "trace_id": item.trace_id or f"trace-{item.tool_id}-{item.id}",
        "created_at": item.created_at,
    }
```

- [ ] **Step 6: Route execution filters all the way through service methods**

```python
rows = await self._repo.list_executions(
    self._org_id,
    tool_id=payload.get("tool_id"),
    agent_id=payload.get("agent_id"),
    status=payload.get("status"),
    execution_type=payload.get("execution_type"),
    page=page,
    size=size,
)
total = await self._repo.count_executions(
    self._org_id,
    tool_id=payload.get("tool_id"),
    agent_id=payload.get("agent_id"),
    status=payload.get("status"),
    execution_type=payload.get("execution_type"),
)
```

- [ ] **Step 7: Run backend tests and verify GREEN**

Run:

```bash
pytest backend/tests/test_tools_api.py -q
```

Expected: PASS, including detail and execution contract tests.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/tool_service.py backend/app/models/tool.py backend/tests/test_tools_api.py
git commit -m "feat: make tool service phase-1 truthful"
```

---

### Task 3: Replace Dry-Run Tool Testing With Real Execution Paths

**Files:**
- Modify: `backend/app/services/tool_service.py`
- Modify: `backend/app/services/tool_sync_service.py`
- Modify: `backend/app/api/v1/tools.py`
- Test: `backend/tests/test_tools_api.py`

- [ ] **Step 1: Write a failing backend test for real tool testing behavior**

```python
@pytest.mark.asyncio
async def test_test_tool_records_test_execution(monkeypatch):
    recorded = {}

    class FakeToolService:
        def __init__(self, db, org_id):
            pass

        async def test_tool(self, tool_id, params):
            recorded["tool_id"] = tool_id
            recorded["params"] = params
            return {
                "status": "success",
                "duration_ms": 12,
                "output": {"ok": True},
                "error": None,
                "trace_id": "trace-1",
            }

    monkeypatch.setattr(tools_api, "ToolService", FakeToolService)
    response = await tools_api.test_tool(
        "tool-1",
        payload=tools_api.ToolTestRequest(params={"query": "hello"}),
        current=current_user(),
        db=object(),
    )
    assert response.data["status"] == "success"
    assert recorded["params"] == {"query": "hello"}
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
pytest backend/tests/test_tools_api.py -k test_tool -q
```

Expected: FAIL before real execution cleanup.

- [ ] **Step 3: Add a real execution dispatcher in ToolService**

```python
async def _execute_tool_for_test(self, tool: ToolRegistry, params: dict[str, Any]) -> Any:
    tool_type = (tool.tool_type or "").lower()
    if tool_type in {"native", "rag"}:
        handler_path = self._derive_handler_path(tool)
        if not handler_path:
            raise ValidationError("tool handler is not configured")
        module_path, func_name = handler_path.rsplit(".", 1)
        module = import_module(module_path)
        handler = getattr(module, func_name)
        result = handler(**params)
        if isawaitable(result):
            return await result
        return result
    if tool_type in {"http", "openapi"}:
        if not tool.endpoint:
            raise ValidationError("tool endpoint is not configured")
        async with httpx.AsyncClient(timeout=tool.timeout_ms / 1000) as client:
            response = await client.post(tool.endpoint, json=params)
            response.raise_for_status()
            return response.json()
    raise ValidationError(f"tool type {tool.tool_type} is not supported in phase 1 testing")
```

- [ ] **Step 4: Update `test_tool` to call the real dispatcher and persist truthful execution results**

```python
async def test_tool(self, tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
    tool = await self._repo.get(self._org_id, tool_id)
    if not tool:
        raise NotFoundError("tool not found")

    started_at = datetime.utcnow()
    status = "success"
    output = None
    error = None
    trace_id = f"tool-test-{tool.id}-{uuid7()}"

    try:
        missing = self._validate_required_params(tool.parameters_schema or {}, params)
        if missing:
            raise ValidationError(f"missing required parameters: {', '.join(missing)}")
        output = await self._execute_tool_for_test(tool, params)
    except Exception as exc:
        status = "failed"
        error = str(exc)

    duration_ms = max(1, int((datetime.utcnow() - started_at).total_seconds() * 1000))
    await self._repo.create_execution(
        ToolExecution(
            id=str(uuid7()),
            task_id=str(uuid7()),
            org_id=self._org_id,
            tool_id=tool.id,
            tool_name=tool.display_name,
            call_index=0,
            input_payload=params,
            output_payload=output if status == "success" else None,
            status=status,
            error_message=error,
            latency_ms=duration_ms,
            execution_type="test",
            trace_id=trace_id,
            input_redacted=params,
            output_redacted=output if status == "success" else None,
        )
    )
    return {
        "status": status,
        "duration_ms": duration_ms,
        "output": output,
        "error": error,
        "trace_id": trace_id,
    }
```

- [ ] **Step 5: Keep only honest downgrade responses for unfinished API endpoints**

```python
from fastapi import HTTPException

@router.get("/bindings", response_model=ResponseEnvelope[object])
async def get_bindings(...):
    raise HTTPException(status_code=501, detail="Agent bindings are planned for phase 2.")
```

Apply the same honest downgrade pattern for binding/version/event-stream endpoints that remain exposed but not implemented.

- [ ] **Step 6: Run backend tests and verify GREEN**

Run:

```bash
pytest backend/tests/test_tools_api.py -q
```

Expected: PASS for tool test API contract coverage.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/tool_service.py backend/app/services/tool_sync_service.py backend/app/api/v1/tools.py backend/tests/test_tools_api.py
git commit -m "feat: replace dry-run tool testing with real phase-1 execution"
```

---

### Task 4: Align Frontend API, Types, And Store To Real Phase-1 Semantics

**Files:**
- Modify: `frontend/src/types/tools.types.ts`
- Modify: `frontend/src/api/tools.api.ts`
- Modify: `frontend/src/stores/tools.store.ts`
- Test: `frontend` typecheck/build

- [ ] **Step 1: Add a failing type-level constraint by removing fake phase-2 assumptions from the store**

```typescript
// Expected shape after cleanup:
export interface ToolDetail extends ToolDefinition {
  active_version_id: string;
  executions: ToolExecutionRecord[];
  endpoint?: string;
  method?: string;
  handler_path?: string;
  parameters_schema: Record<string, unknown>;
  returns_schema: Record<string, unknown>;
  auth_type: string;
  secret_ref?: string;
  timeout_ms: number;
  retry_policy?: Record<string, unknown>;
  rate_limit_rpm: number;
}
```

This should break any component/store code that still assumes `versions`, `bindings`, or `audit_logs` are always present in phase 1.

- [ ] **Step 2: Run frontend typecheck and verify RED**

Run:

```bash
npm run typecheck
```

Expected: FAIL anywhere the UI still depends on fake phase-2 detail fields.

- [ ] **Step 3: Make phase-1 APIs default to real backend**

```typescript
export const toolsApi = {
  async getOverview() {
    return http.get("/v1/tools/overview");
  },
  async listTools(query: ToolListQuery = {}) {
    return http.get("/v1/tools", { params: query });
  },
  async getTool(id: string) {
    return http.get(`/v1/tools/${id}`);
  },
  async testTool(toolId: string, params: Record<string, unknown>) {
    return http.post(`/v1/tools/${toolId}/test`, { params });
  },
  async listExecutions(query: ExecutionListQuery = {}) {
    return http.get("/v1/tools/executions", { params: query });
  },
  async getExecutionOverview() {
    return http.get("/v1/tools/executions/overview");
  },
  async syncBuiltin() {
    return http.post("/v1/tools/sync/builtin");
  },
};
```

Do not let `previewMocks` hijack these phase-1 calls by default.

- [ ] **Step 4: Remove phase-2 assumptions from the store**

```typescript
async function fetchToolDetail(id: string) {
  currentToolLoading.value = true;
  try {
    const { data } = await toolsApi.getTool(id);
    currentTool.value = data.data;
  } finally {
    currentToolLoading.value = false;
  }
}
```

Keep the store focused on:

1. overview
2. tools list
3. current tool
4. test result
5. executions
6. execution overview

Do not keep live binding matrix state in phase 1 if the page is downgraded.

- [ ] **Step 5: Run frontend typecheck and verify GREEN**

Run:

```bash
npm run typecheck
```

Expected: PASS for tool-related types/store/API alignment.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/tools.types.ts frontend/src/api/tools.api.ts frontend/src/stores/tools.store.ts
git commit -m "feat: align tool frontend data layer to real phase-1 backend"
```

---

### Task 5: Make The Four Phase-1 Pages Truthful And Downgrade The Rest

**Files:**
- Modify: `frontend/src/views/ops/tools/ToolOverviewView.vue`
- Modify: `frontend/src/views/ops/tools/ToolCatalogView.vue`
- Modify: `frontend/src/views/ops/tools/ToolDetailView.vue`
- Modify: `frontend/src/views/ops/tools/ToolExecutionView.vue`
- Modify: `frontend/src/views/ops/tools/ToolImportView.vue`
- Modify: `frontend/src/views/ops/tools/ToolBindingView.vue`
- Modify: `frontend/src/router/routes/ops.routes.ts`
- Modify: `frontend/src/composables/useMenu.ts`

- [ ] **Step 1: Break the current phase-2 tabs in detail view on purpose**

Replace the detail tabs list with phase-1 only tabs:

```vue
<el-tabs v-model="activeTab" class="detail-tabs">
  <el-tab-pane label="概览" name="overview" />
  <el-tab-pane label="配置" name="config" />
  <el-tab-pane label="参数 Schema" name="schema" />
  <el-tab-pane label="测试" name="test" />
  <el-tab-pane label="执行记录" name="executions" />
</el-tabs>
```

This should force removal of bindings/version/audit assumptions.

- [ ] **Step 2: Run frontend build or typecheck and verify RED**

Run:

```bash
npm run build
```

Expected: FAIL until phase-2 references are removed from the pages.

- [ ] **Step 3: Update ToolCatalogView to use real phase-1 filters**

```typescript
const filterCategory = ref<ToolCategory | "">("");
const filterStatus = ref<ToolStatus | "">("");
const filterRisk = ref<RiskLevel | "">("");
const filterSource = ref<SourceType | "">("");

async function loadTools() {
  await store.fetchTools({
    page: currentPage.value,
    size: pageSize.value,
    keyword: keyword.value || undefined,
    category: filterCategory.value || undefined,
    status: filterStatus.value || undefined,
    risk_level: filterRisk.value || undefined,
    source_type: filterSource.value || undefined,
  });
}
```

Also remove the fake `has_binding` filter if phase 1 cannot back it truthfully.

- [ ] **Step 4: Update ToolExecutionView to pass real filters only**

```typescript
async function loadExecutions() {
  await store.fetchExecutions({
    page: currentPage.value,
    size: pageSize.value,
    status: filterStatus.value || undefined,
    execution_type: filterType.value || undefined,
  });
}
```

Make sure the page labels and chart labels are clean Chinese strings, not mojibake.

- [ ] **Step 5: Downgrade import and binding pages honestly**

For `ToolImportView.vue`:

```vue
<el-alert
  type="info"
  :closable="false"
  title="外部导入将在第二、三阶段开放"
  description="当前阶段仅支持内置工具同步到工具库，不提供 OpenAPI 或 MCP 的真实导入流程。"
  show-icon
/>

<el-button type="primary" :loading="syncing" @click="runBuiltinSync">
  同步内置工具
</el-button>
```

For `ToolBindingView.vue`:

```vue
<el-empty description="Agent 绑定将在第二阶段开放">
  <template #description>
    <span>当前开发环境仅交付第一阶段工具管理能力，真实 Agent 绑定矩阵未在本轮启用。</span>
  </template>
</el-empty>
```

- [ ] **Step 6: Hide or demote second-phase menu exposure**

```typescript
{ path: "tools/import", ...meta: { title: "外部导入（规划中）", roles: TOOL_MANAGEMENT_ROLES } }
{ path: "tools/bindings", ...meta: { title: "Agent 绑定（规划中）", roles: TOOL_MANAGEMENT_ROLES } }
```

If the menu helper makes hiding cleaner, remove them from `useMenu.ts` for this phase.

- [ ] **Step 7: Run frontend build and verify GREEN**

Run:

```bash
npm run build
```

Expected: PASS, with only phase-1 pages doing real work.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/ops/tools frontend/src/router/routes/ops.routes.ts frontend/src/composables/useMenu.ts
git commit -m "feat: make tool phase-1 pages truthful and downgrade deferred flows"
```

---

### Task 6: Update Tool Docs And Verify The Whole Vertical Slice

**Files:**
- Modify: `docs/tool_management.md`
- Test: backend pytest, frontend typecheck/build/lint

- [ ] **Step 1: Update `docs/tool_management.md` so phase-1 matches reality**

Rewrite the current-state and rollout sections so they say:

```md
- 第一阶段：真实可用
  - 工具总览
  - 工具库
  - 工具详情（概览/配置/Schema/测试/执行记录）
  - 执行监控
  - 内置工具同步

- 第二阶段：待实现
  - 版本历史
  - Agent 绑定

- 第三阶段：待实现
  - OpenAPI / MCP 导入
  - SSE / WebSocket
  - 安全审批
```

- [ ] **Step 2: Run backend tests**

Run:

```bash
pytest backend/tests/test_tools_api.py
```

Expected: PASS.

- [ ] **Step 3: Run frontend typecheck**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 5: Run frontend lint and inspect only current-scope failures**

Run:

```bash
cd frontend && npm run lint
```

Expected: Tool-management-related lint issues are fixed. If unrelated repo-wide history debt remains, document it explicitly instead of hiding it.

- [ ] **Step 6: Commit**

```bash
git add docs/tool_management.md
git commit -m "docs: align tool management spec with real phase-1 delivery"
```

---

## Self-Review

### Spec coverage

- Real phase-1 backend endpoints: covered by Tasks 1-3.
- Real phase-1 frontend pages: covered by Tasks 4-5.
- Honest downgrade of unfinished bindings/import/versioning/realtime: covered by Tasks 3 and 5.
- Docs alignment and verification: covered by Task 6.

### Placeholder scan

- No `TBD`, `TODO`, or “implement later” placeholders remain.
- Deferred capabilities are described as explicit downgrade work, not as vague future intention.

### Type consistency

- `status` remains lifecycle status.
- `health_status` remains runtime health.
- `execution_type` is treated consistently across backend repository, service, API, frontend types, and execution monitor UI.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-21-tool-management-phase1.md`. Since you already asked me to execute and didn’t request subagent delegation, I’ll use inline execution and start with the backend phase-1 fixes. 
