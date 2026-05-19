# PIAP 路由策略查看中心 实施计划

> **Spec:** `docs/PIAP_Router.md`
> **原则:** 先不做路由配置与发布，只把当前真实路由逻辑清晰展示、可模拟、可观测、可诊断
> **目标页面:** `/ops/agents/intent-routes`
> **设计原则:** 页面动态展示真实路由逻辑，而非静态文字。减少大段文字，多用流程图/规则卡片/路由树/事件列表

**Goal:** 将路由策略页面从文字堆叠的说明页升级为清晰、可信、可诊断的路由策略查看中心

**Architecture:** 后端新增4个API（routing/current, routing/simulate, routing/events, routing/metrics），前端 IntentRouteView.vue 完全重写为三栏布局（路由树 + 决策流图 + 规则详情）+ 模拟器 + 事件表

**Tech Stack:** Python/FastAPI (后端), Vue3/TypeScript/ElementPlus/ECharts (前端)

---

## 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| MODIFY | `backend/app/schemas/agent_ops.py` | 新增 10 个路由查看 Schema |
| MODIFY | `backend/app/services/agent_ops_service.py` | 新增 4 个方法 |
| MODIFY | `backend/app/api/v1/agent_ops.py` | 新增 4 个 API 端点 |
| MODIFY | `frontend/src/types/agent-ops.types.ts` | 新增 8 个前端类型 |
| MODIFY | `frontend/src/api/agent-ops.api.ts` | 新增 4 个 API 调用 |
| MODIFY | `frontend/src/stores/agent-ops.store.ts` | 新增 state + actions |
| REWRITE | `frontend/src/views/ops/IntentRouteView.vue` | 完全重写 |

---

### Task 1: 后端 Schema 新增

**Files:** MODIFY `backend/app/schemas/agent_ops.py`

在文件末尾新增 10 个 Pydantic Schema：

```python
# === Routing Strategy Viewer schemas ===

class RouteAgentDescriptor(BaseModel):
    key: str  # "chat" | "inspection_task"
    label: str
    sub_routes: list[str] = Field(default_factory=list)

class RouteRuleDescriptor(BaseModel):
    priority: int
    name: str
    condition_summary: str
    target_agent: str
    target_sub_route: str
    route_source: str = "builtin"
    examples: list[str] = Field(default_factory=list)

class RouteSignalInfo(BaseModel):
    key: str
    label: str
    description: str
    detected: bool = False

class RoutingCurrentResponse(BaseModel):
    mode: str = "rule_first_with_model_fallback"
    mode_label: str = "规则优先，模型兜底"
    default_agent: str = "chat"
    default_sub_route: str = "general_chat"
    agents: list[RouteAgentDescriptor] = Field(default_factory=list)
    rules: list[RouteRuleDescriptor] = Field(default_factory=list)
    signals: list[RouteSignalInfo] = Field(default_factory=list)
    rule_count: int = 0
    active_agent_count: int = 0

class RouteSimulateRequest(BaseModel):
    query: str = Field(default="")
    has_image: bool = Field(default=False)
    has_structured_file: bool = Field(default=False)
    has_rag_space: bool = Field(default=False)
    force_agent: Optional[str] = Field(default=None)

class RouteSimulateResponse(BaseModel):
    matched_rule_name: str = ""
    matched_priority: int = 0
    selected_agent: str = ""
    selected_sub_route: str = ""
    route_source: str = ""
    reason: str = ""
    signals: dict = Field(default_factory=dict)
    is_fallback: bool = False

class RouteEventItem(BaseModel):
    id: str
    created_at: datetime
    selected_agent: str
    sub_route: Optional[str] = None
    route_source: str
    reason: Optional[str] = None
    intent_name: Optional[str] = None
    confidence: float = 0.0
    latency_ms: int = 0
    blocked: bool = False
    blocked_reason: Optional[str] = None
    request_summary: Optional[str] = None
    model_config = {"from_attributes": True}

class RoutingMetricsResponse(BaseModel):
    total_24h: int = 0
    rule_hit_count: int = 0
    model_fallback_count: int = 0
    blocked_count: int = 0
    avg_latency_ms: float = 0.0
    by_agent: dict = Field(default_factory=dict)
    by_rule: dict = Field(default_factory=dict)
```

---

### Task 2: 后端 Service — 路由策略查看方法

**Files:** MODIFY `backend/app/services/agent_ops_service.py`

新增 4 个方法到 `AgentOpsService` 类：

#### get_routing_current() — 返回真实路由结构

不读数据库，直接返回基于 `route_policy.py` 真实代码的路由策略。真实路由结构只有 `chat` 和 `inspection_task` 两个 Agent：

```python
async def get_routing_current(self) -> RoutingCurrentResponse:
    return RoutingCurrentResponse(
        mode="rule_first_with_model_fallback",
        mode_label="规则优先，模型兜底",
        default_agent="chat",
        default_sub_route="general_chat",
        agents=[
            RouteAgentDescriptor(key="chat", label="Quality Chat", sub_routes=["general_chat", "rag_qa"]),
            RouteAgentDescriptor(key="inspection_task", label="Inspection Task Agent", sub_routes=["task_create", "inspection_execute", "quality_qa"]),
        ],
        rules=[
            RouteRuleDescriptor(priority=1, name="手动指定检测", condition_summary="前端 force_agent=inspection_task", target_agent="inspection_task", target_sub_route="task_create", route_source="manual", examples=["force_agent=inspection_task"]),
            RouteRuleDescriptor(priority=2, name="手动指定聊天", condition_summary="前端 force_agent=chat", target_agent="chat", target_sub_route="general_chat", route_source="manual", examples=["force_agent=chat"]),
            RouteRuleDescriptor(priority=3, name="文件+检测意图", condition_summary="xlsx/csv/json等文件 + 检测/质检关键词", target_agent="inspection_task", target_sub_route="inspection_execute", examples=["上传Excel+创建检测"]),
            RouteRuleDescriptor(priority=4, name="图片+检测意图", condition_summary="图片附件/URL + 检测/质检关键词", target_agent="inspection_task", target_sub_route="inspection_execute", examples=["图片+帮我检测"]),
            RouteRuleDescriptor(priority=5, name="任务创建意图", condition_summary="纯文本含任务关键词", target_agent="inspection_task", target_sub_route="task_create", examples=["创建检测任务", "帮我检测"]),
            RouteRuleDescriptor(priority=6, name="质检问答意图", condition_summary="含质检语义关键词", target_agent="inspection_task", target_sub_route="quality_qa", examples=["这个算缺陷吗", "按标准判定"]),
            RouteRuleDescriptor(priority=7, name="RAG知识库问答", condition_summary="选中RAG空间或知识库意图", target_agent="chat", target_sub_route="rag_qa", examples=["根据知识库回答"]),
            RouteRuleDescriptor(priority=8, name="模糊输入兜底", condition_summary="短句/代词/无明确意图", target_agent="chat", target_sub_route="general_chat", route_source="rule", examples=["这个呢", "看看"]),
            RouteRuleDescriptor(priority=9, name="默认普通聊天", condition_summary="兜底规则", target_agent="chat", target_sub_route="general_chat", examples=["你好"]),
        ],
        signals=[
            RouteSignalInfo(key="has_task_keyword", label="任务意图关键词", description="文本包含创建任务、提交任务等关键词"),
            RouteSignalInfo(key="has_images", label="图片附件", description="请求包含图片附件或URL"),
            RouteSignalInfo(key="has_structured_file", label="结构化文件", description="请求包含xlsx/csv/json等文件"),
            RouteSignalInfo(key="has_quality_signal", label="质检语义", description="文本含质量、缺陷、合格等关键词"),
            RouteSignalInfo(key="has_rag_space", label="RAG空间", description="用户选择了RAG空间"),
            RouteSignalInfo(key="is_ambiguous", label="模糊输入", description="短句、代词多、无明确意图"),
        ],
        rule_count=9, active_agent_count=2,
    )
```

#### simulate_route() — 调用真实路由决策

调用 `AgentRoutePolicy.decide()` 但不执行 Agent：

```python
async def simulate_route(self, body: RouteSimulateRequest) -> RouteSimulateResponse:
    from agent.router.route_policy import AgentRoutePolicy
    from agent.router.contracts import AgentRouterInput

    route_hints = {}
    if body.force_agent:
        route_hints["force_agent"] = body.force_agent

    attachments = []
    if body.has_image:
        attachments.append({"kind": "image", "name": "test.png"})
    if body.has_structured_file:
        attachments.append({"kind": "file", "name": "test.xlsx"})

    ext = {}
    if body.has_rag_space:
        ext["selected_rag_space"] = {"id": "test-space"}

    policy = AgentRoutePolicy()
    decision = policy.decide(AgentRouterInput(
        query=body.query, request_kind="chat",
        attachments=attachments, image_urls=[], route_hints=route_hints, ext=ext,
    ))

    # Map to rule name
    rule_map = {
        ("inspection_task", "inspection_execute"): ("文件/图片+检测意图", 3),
        ("inspection_task", "task_create"): ("任务创建意图", 5),
        ("inspection_task", "quality_qa"): ("质检问答意图", 6),
        ("chat", "rag_qa"): ("RAG知识库问答", 7),
        ("chat", "general_chat"): ("默认普通聊天", 9),
    }
    rule_name, priority = rule_map.get((decision.selected_agent, decision.sub_route), (decision.reason, 0))
    if decision.route_source == "manual":
        rule_name = "手动指定" + ("检测" if decision.selected_agent == "inspection_task" else "聊天")
        priority = 1 if decision.selected_agent == "inspection_task" else 2

    return RouteSimulateResponse(
        matched_rule_name=rule_name, matched_priority=priority,
        selected_agent=decision.selected_agent, selected_sub_route=decision.sub_route,
        route_source=decision.route_source, reason=decision.reason,
        signals={
            "has_task_keyword": bool(body.query and any(kw in body.query for kw in ["任务", "检测", "创建", "提交"])),
            "has_images": body.has_image,
            "has_structured_file": body.has_structured_file,
            "has_quality_signal": bool(body.query and any(kw in body.query for kw in ["质量", "缺陷", "合格", "标准"])),
            "has_rag_space": body.has_rag_space,
        },
        is_fallback=decision.fallback_agent == "model_classifier",
    )
```

#### get_routing_events() — 从 agent_route_logs 读取

```python
async def get_routing_events(self, limit: int = 20) -> list[RouteEventItem]:
    from app.models.agent_ops import AgentRouteLog
    from sqlalchemy import select

    result = await self._session.execute(
        select(AgentRouteLog)
        .where(AgentRouteLog.org_id == self._org_id, AgentRouteLog.deleted_at.is_(None))
        .order_by(AgentRouteLog.created_at.desc())
        .limit(limit)
    )
    items = []
    for row in result.scalars().all():
        request_summary = None
        sig = row.signals_json or {}
        if isinstance(sig, dict):
            parts = [k for k, v in sig.items() if v]
            request_summary = f"signals: {', '.join(parts)}" if parts else None
        items.append(RouteEventItem(
            id=str(row.id), created_at=row.created_at,
            selected_agent=row.selected_agent, sub_route=row.sub_route,
            route_source=row.route_source or "rule", reason=row.reason,
            intent_name=row.intent_name, confidence=float(row.confidence or 0.0),
            latency_ms=row.latency_ms or 0,
            blocked=bool(row.blocked), blocked_reason=row.blocked_reason,
            request_summary=request_summary,
        ))
    return items
```

#### get_routing_metrics() — 24h 统计

```python
async def get_routing_metrics(self) -> RoutingMetricsResponse:
    from app.models.agent_ops import AgentRouteLog
    from sqlalchemy import select
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(hours=24)
    result = await self._session.execute(
        select(AgentRouteLog).where(
            AgentRouteLog.org_id == self._org_id,
            AgentRouteLog.created_at >= cutoff,
            AgentRouteLog.deleted_at.is_(None),
        )
    )
    rows = list(result.scalars().all())
    total = len(rows)
    return RoutingMetricsResponse(
        total_24h=total,
        rule_hit_count=sum(1 for r in rows if r.route_source == "rule"),
        model_fallback_count=sum(1 for r in rows if r.route_source == "model"),
        blocked_count=sum(1 for r in rows if r.blocked),
        avg_latency_ms=round(sum(r.latency_ms or 0 for r in rows) / max(total, 1), 2),
        by_agent={a: sum(1 for r in rows if r.selected_agent == a) for a in set(r.selected_agent for r in rows if r.selected_agent)},
        by_rule={f"{r.selected_agent}/{r.sub_route}": sum(1 for x in rows if x.selected_agent == r.selected_agent and x.sub_route == r.sub_route) for r in rows if r.selected_agent},
    )
```

---

### Task 3: 后端 API 端点

**Files:** MODIFY `backend/app/api/v1/agent_ops.py`

新增 4 个端点（在现有 `/routing/strategy` 附近）：

```python
@router.get("/routing/current", response_model=RoutingCurrentResponse)
async def get_routing_current(
    org_id: str = Depends(require_org_scope),
    actor_id: str = Depends(require_actor_id),
    session: AsyncSession = Depends(get_session),
):
    """获取当前系统真实路由策略视图"""
    service = AgentOpsService(session, org_id, actor_id)
    return await service.get_routing_current()


@router.post("/routing/simulate", response_model=RouteSimulateResponse)
async def simulate_route(
    body: RouteSimulateRequest, ...):
    """模拟路由 — 调用真实路由决策逻辑，不执行Agent"""
    service = AgentOpsService(session, org_id, actor_id)
    return await service.simulate_route(body)


@router.get("/routing/events", response_model=list[RouteEventItem])
async def get_routing_events(
    limit: int = Query(default=20, ge=1, le=100), ...):
    """获取最近路由事件"""
    service = AgentOpsService(session, org_id, actor_id)
    return await service.get_routing_events(limit=limit)


@router.get("/routing/metrics", response_model=RoutingMetricsResponse)
async def get_routing_metrics(...):
    """获取路由统计指标（最近24h）"""
    service = AgentOpsService(session, org_id, actor_id)
    return await service.get_routing_metrics()
```

---

### Task 4: 前端类型定义

**Files:** MODIFY `frontend/src/types/agent-ops.types.ts`

新增接口：

```typescript
export interface RouteAgentDescriptor {
  key: string; label: string; sub_routes: string[];
}
export interface RouteRuleDescriptor {
  priority: number; name: string; condition_summary: string;
  target_agent: string; target_sub_route: string;
  route_source: string; examples: string[];
}
export interface RouteSignalInfo {
  key: string; label: string; description: string; detected: boolean;
}
export interface RoutingCurrent {
  mode: string; mode_label: string;
  default_agent: string; default_sub_route: string;
  agents: RouteAgentDescriptor[]; rules: RouteRuleDescriptor[];
  signals: RouteSignalInfo[]; rule_count: number; active_agent_count: number;
}
export interface RouteSimulateRequest {
  query: string; has_image: boolean; has_structured_file: boolean;
  has_rag_space: boolean; force_agent?: string;
}
export interface RouteSimulateResult {
  matched_rule_name: string; matched_priority: number;
  selected_agent: string; selected_sub_route: string;
  route_source: string; reason: string;
  signals: Record<string, boolean>; is_fallback: boolean;
}
export interface RouteEventItem {
  id: string; created_at: string; selected_agent: string;
  sub_route?: string; route_source: string; reason?: string;
  intent_name?: string; confidence: number; latency_ms: number;
  blocked: boolean; blocked_reason?: string; request_summary?: string;
}
export interface RoutingMetrics {
  total_24h: number; rule_hit_count: number; model_fallback_count: number;
  blocked_count: number; avg_latency_ms: number;
  by_agent: Record<string, number>; by_rule: Record<string, number>;
}
```

---

### Task 5: 前端 API 和 Store

**Files:** MODIFY `frontend/src/api/agent-ops.api.ts`, `frontend/src/stores/agent-ops.store.ts`

**API 新增:**
```typescript
getRoutingCurrent: () => http.get<RoutingCurrent>("/v1/agent-ops/routing/current"),
simulateRoute: (data: RouteSimulateRequest) => http.post<RouteSimulateResult>("/v1/agent-ops/routing/simulate", data),
getRoutingEvents: (limit?: number) => http.get<RouteEventItem[]>("/v1/agent-ops/routing/events", { params: { limit } }),
getRoutingMetrics: () => http.get<RoutingMetrics>("/v1/agent-ops/routing/metrics"),
```

**Store 新增:**
```typescript
const routingCurrent = ref<RoutingCurrent | null>(null);
const simulateResult = ref<RouteSimulateResult | null>(null);
const routingEvents = ref<RouteEventItem[]>([]);
const routingMetrics = ref<RoutingMetrics | null>(null);

async function fetchRoutingCurrent() { ... }
async function simulateRoute(data: RouteSimulateRequest) { ... }
async function fetchRoutingEvents(limit = 20) { ... }
async function fetchRoutingMetrics() { ... }
```

---

### Task 6: IntentRouteView.vue 完全重写

**Files:** REWRITE `frontend/src/views/ops/IntentRouteView.vue`

使用 `impeccable` (frontend-design) 技能实现。

**页面布局：**

```
┌─────────────────────────────────────────────────────┐
│ 路由策略                                              │
│ 查看当前系统真实路由逻辑、模拟路由结果、观测最近路由事件    │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┤
│ 路由模式   │ 默认目标   │ 内置规则   │ 参与Agent  │ 24h 路由  │ 异常路由   │
│ 规则优先   │ chat/     │ 9 条      │ 2 个      │ 1253 次   │ 0 次     │
│ 模型兜底   │ general.. │           │           │           │           │
├──────────┴──────────┴──────────┴──────────┴──────────┴──────────┤
│                  │                          │                   │
│  Agent 路由树    │  路由决策流图 (ECharts)    │  规则详情面板       │
│                  │  固定横向6层布局           │                   │
│  Agent Manager   │  请求→Manager→信号→       │  名称/优先级/       │
│  ├ Quality Chat  │  规则→Agent→子路由        │  目标/条件/示例     │
│  │ ├ general_chat│                          │                   │
│  │ └ rag_qa     │                          │                   │
│  └ Inspection    │                          │                   │
│    ├ task_create │                          │                   │
│    ├ inspection..│                          │                   │
│    └ quality_qa │                          │                   │
│                  │                          │                   │
├──────────────────────────────────┬──────────────────────────────┤
│  当前内置规则表（只读）             │  路由模拟器                    │
│  P1-P9 规则列表                   │  输入文本 + 图片/文件/RAG勾选   │
│  点击规则高亮图中路径              │  模拟结果展示                  │
├──────────────────────────────────┴──────────────────────────────┤
│  最近路由事件 (从 agent_route_logs 实时读取)                       │
│  时间 | 状态 | Agent | 子路由 | 来源 | 原因 | 延迟                 │
└──────────────────────────────────────────────────────────────────┘
```

**核心设计要点：**

1. **决策流图** — ECharts `layout: "none"` 固定横向6层：
   - Layer 1: 用户请求
   - Layer 2: Agent Manager
   - Layer 3: 信号识别 (任务意图/图片/文件/质检/RAG/模糊)
   - Layer 4: 规则匹配 (P1-P9)
   - Layer 5: 目标 Agent (Quality Chat / Inspection Task)
   - Layer 6: 子路由 (general_chat/rag_qa/task_create/inspection_execute/quality_qa)

2. **动态联动：**
   - 点击左侧路由树Agent → 中间图高亮对应Agent节点和子路由
   - 点击规则表行 → 中间图高亮对应规则路径，右侧显示规则详情
   - 模拟器执行后 → 中间图高亮命中路径

3. **颜色编码：**
   - 蓝色 `#6366f1` — 请求入口
   - 蓝色 `#2563eb` — Agent Manager
   - 灰色 `#94a3b8` — 信号节点
   - 绿色 `#0d9488` — Quality Chat 及子路由
   - 琥珀 `#d97706` — Inspection Task 及子路由
   - 红色 `#dc2626` — 异常/阻止

4. **动态数据来源：**
   - `GET /routing/current` — 页面加载时获取
   - `GET /routing/metrics` — 顶部指标卡
   - `GET /routing/events` — 底部事件表
   - `POST /routing/simulate` — 用户点击模拟时调用

5. **删除的内容：**
   - 删除 `intent-route-fallback.ts` 静态兜底
   - 删除旧版 ECharts 力导向图（旧 layout）
   - 删除大段文字说明
   - 删除 `legacy_quality` / `llm_native_quality` 等旧概念展示

---

### Task 7: 验证

- [ ] `cd backend && python -c "from app.schemas.agent_ops import RoutingCurrentResponse; from app.api.v1.agent_ops import router; print('OK')"`
- [ ] `cd frontend && npx vue-tsc --noEmit 2>&1 | grep "IntentRouteView"`
- [ ] 页面加载后顶部指标卡显示正确
- [ ] 决策流图渲染6层横向布局
- [ ] 点击路由树Agent节点 → 图中高亮
- [ ] 点击规则表行 → 右侧显示详情 + 图高亮
- [ ] 模拟器：输入"检测图片" + 勾选图片 → 结果指向 inspection_task/inspection_execute
- [ ] 模拟器：输入"你好" → 结果指向 chat/general_chat
- [ ] 最近路由事件表显示 agent_route_logs 数据
- [ ] 页面不显示 legacy_quality/llm_native_quality 等旧概念

---

## 实施顺序

```
Task 1 → Task 2 → Task 3  (后端：Schema → Service → API)
Task 4 → Task 5           (前端：类型 → API+Store)
Task 6                     (前端：IntentRouteView 完全重写)
Task 7                     (验证)
```
