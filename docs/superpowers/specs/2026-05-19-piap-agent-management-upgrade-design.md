# PIAP Agent 管理页面产品化改造设计

> 基于 `docs/PIAP_Agent.md` v1.0
> 实施范围：P0 + P1
> 实施策略：全栈逐层（数据模型 → 后端服务 → API → 前端）

---

## 1. 目标

将 `/ops/agents` 页面从展示型页面升级为真实可信的 **AgentOps 控制台**。页面保持三个模块（定义/运行态/拓扑）不变。

### P0（必须先做）
1. 清理旧 Agent 展示，不再让历史 Agent 显示为正常 running
2. 增加 lifecycle_status、group_key、route_enabled
3. 修复停止操作，使其真实影响路由
4. AgentManager 执行前检查运行态
5. 规划中 Agent 显示为"规划中 / 仅展示"

### P1（提升体验）
1. Agent 分组展示
2. Agent 详情抽屉
3. 操作确认弹窗
4. 运行态审计日志
5. 拓扑图区分设计拓扑和运行拓扑
6. 节点点击详情
7. 最近路由日志

---

## 2. Agent 清单

保留 topology_catalog.py 中现有 9 个 Agent，分为两组：

**核心运行链路（4 个）**：Agent Manager、Quality Chat、Inspection Task Agent、Quality Judgement
- lifecycle_status=active, group=core, route_enabled=true

**专业规划 Agent（5 个）**：Market Monitor、Public Opinion、Trend Evolution、Supervision Sampling、Lab Detection
- lifecycle_status=planned, group=planned, route_enabled=false, is_active=false

已删除 Agent：Legacy Quality、LLM-native Quality、Shared Memory Hierarchy（数据库中如有残留，同步时自动标记为 deprecated）。

---

## 3. 数据库变更（Alembic 迁移 0035）

### 3.1 agent_definitions 新增字段
- `lifecycle_status` VARCHAR(32) DEFAULT 'active' — active/partial/planned/legacy/deprecated
- `group_key` VARCHAR(32) DEFAULT 'core' — core/memory/planned/legacy
- `route_enabled` BOOLEAN DEFAULT TRUE
- `supports_route_toggle` BOOLEAN DEFAULT TRUE
- `customer_visible_description` TEXT NULLABLE

### 3.2 agent_runtime_instances 新增字段
- `runtime_status` VARCHAR(32) DEFAULT 'stopped' — running/stopped/degraded/maintenance/readonly (原 status 字段保留兼容，新字段名更语义化)
- `last_health_check_at` DATETIME NULLABLE
- `last_error_message` TEXT NULLABLE
- `last_error_at` DATETIME NULLABLE
- `maintenance_reason` TEXT NULLABLE
- `updated_by` BINARY(16) NULLABLE

### 3.3 新建 agent_runtime_events 表
- `id` BINARY(16) PK
- `org_id` BINARY(16) INDEX
- `agent_id` BINARY(16) INDEX
- `runtime_key` VARCHAR(128)
- `event_type` VARCHAR(32) — pause_route/resume_route/start/stop/maintenance
- `before_status` VARCHAR(32)
- `after_status` VARCHAR(32)
- `reason` TEXT NULLABLE
- `operator_id` BINARY(16) NULLABLE
- `created_at` DATETIME

### 3.4 agent_route_logs 新增字段
- `blocked` BOOLEAN DEFAULT FALSE
- `blocked_reason` TEXT NULLABLE

---

## 4. 后端改造

### 4.1 topology_catalog.py
为 9 个 Agent 补充 `lifecycle_status`, `group`, `route_enabled`, `supports_route_toggle`, `customer_visible_description`。修改 `get_registered_subgraphs()` 返回完整字段。

### 4.2 agent_manager.py（P0 关键）
新增 `agent/router/runtime_guard.py` — `AgentRuntimeGuard` 类：
- `check(org_id, selected_agent, sub_route)` → 查询对应 Agent runtime 记录
- 检查 `route_enabled=True` 且 `runtime_status in (running, degraded)`
- 不通过返回 blocked=True + reason + customer_message

AgentManager.run() 中在 route_policy.decide() 之后、agent 执行之前插入守卫检查。被阻止时返回 `status="blocked"` 的 AgentRouterOutput。

### 4.3 agent_ops_service.py
- `_sync_registered_agents()`：数据库存在但 catalog 不存在的 Agent → 自动标记 `lifecycle_status=deprecated, route_enabled=false, is_active=false, runtime_status=stopped`
- `set_runtime_status()`：状态变更写入 `agent_runtime_events` 审计表
- 新增方法：`pause_route(runtime_key, reason)`, `resume_route(runtime_key)` 
- 运行态概览增强：增加今日执行、成功率、最近错误统计

### 4.4 agent_ops API 端点新增
- `POST /v1/agent-ops/runtime/agents/{runtime_key}/pause-route` — body: `{reason: str}`
- `POST /v1/agent-ops/runtime/agents/{runtime_key}/resume-route`
- `GET /v1/agent-ops/agents/topology?mode=runtime|design` — 支持 mode 参数
- `GET /v1/agent-ops/agents/{id}/detail` — 返回 Agent 完整详情（含绑定资源、操作记录）
- `GET /v1/agent-ops/runtime/events?agent_id=&limit=` — 运行态事件日志

### 4.5 ORM 模型更新
- `AgentDefinition` 新增 lifecycle_status, group_key, route_enabled, supports_route_toggle, customer_visible_description
- `AgentRuntimeInstance` 新增 runtime_status, last_health_check_at, last_error_message, last_error_at, maintenance_reason, updated_by
- 新建 `AgentRuntimeEvent` 模型
- `AgentRouteLog` 新增 blocked, blocked_reason

### 4.6 Schemas 更新
- `AgentDefinitionResponse` 新增 lifecycle_status, group_key, route_enabled, supports_route_toggle, customer_visible_description
- `AgentRuntimeInstanceResponse` 新增 runtime_status, last_error_message, maintenance_reason, updated_by
- 新增 `AgentRuntimeEventResponse`, `AgentDetailResponse`
- `AgentRuntimeOverviewResponse` 新增 success_rate, recent_errors

---

## 5. 前端改造

### 5.1 路由与菜单收敛
**ops.routes.ts**：删除 `/ops/agents/topology`(Placeholder), `/ops/workflows`(Placeholder), `/ops/tools`(Placeholder), `/ops/releases`(Placeholder)。

**useMenu.ts**：移除菜单中"Agent 拓扑图"、"流程节点"、"工具注册"、"发布管理"占位项。

### 5.2 定义 Tab
- **顶部概览卡片**：核心Agent / 规划中Agent / 历史Agent / 可控制Agent / 异常Agent
- **表格字段**：名称、类型标签(core/planned/legacy)、能力说明、接入状态、参与路由、运行态、指标（执行数/成功率/平均延迟）、操作
- **筛选增强**：按类型(group_key)、接入状态(lifecycle_status)筛选
- **详情抽屉**（点击行打开）：基础信息、能力说明、路由信息、绑定资源、运行指标、操作记录

### 5.3 运行态 Tab
- **顶部卡片增强**：运行中/已暂停/今日执行/成功率/平均延迟/最近错误
- **操作按钮升级**：
  - 核心Agent：暂停路由/恢复路由/进入维护/查看日志
  - 规划中Agent：仅展示（按钮置灰）
  - 历史Agent：已废弃（按钮置灰）
- **操作确认弹窗**：暂停时显示影响范围 + 原因输入 + 确认/取消
- **状态标签**：running(绿)/stopped(灰)/degraded(黄)/maintenance(橙)/readonly(蓝)

### 5.4 拓扑 Tab
- **二级切换**：设计拓扑 / 运行拓扑
- **节点颜色**：绿色(运行)/黄色(部分接入)/灰色(规划中)/橙色(历史)/红色(错误)
- **交互**：点击节点查看详情、高亮调用路径、支持隐藏规划/历史Agent
- **ECharts 力导向图**优化：节点按 group 着色、hover 显示执行指标

### 5.5 类型定义 (agent-ops.types.ts)
新增：
```ts
type AgentLifecycleStatus = "active" | "partial" | "planned" | "legacy" | "deprecated";
type AgentRuntimeStatus = "running" | "stopped" | "degraded" | "maintenance" | "readonly";
type AgentGroup = "core" | "memory" | "planned" | "legacy";
```

AgentDefinition 接口增加：lifecycle_status, group_key, route_enabled, supports_route_toggle, customer_visible_description

### 5.6 Store & API 更新
- `agent-ops.store.ts`：新增 pauseRoute/resumeRoute、fetchAgentDetail、fetchRuntimeEvents actions
- `agent-ops.api.ts`：对应新增 API 调用

---

## 6. 实施顺序

| 步骤 | 内容 | 涉及文件 |
|------|------|----------|
| 1 | Alembic 迁移 0035 | migrations/versions/0035_agent_ops_productize.py |
| 2 | ORM 模型更新 | models/agent_ops.py |
| 3 | topology_catalog 补充字段 | agent/topology_catalog.py |
| 4 | AgentRuntimeGuard 新建 | agent/router/runtime_guard.py |
| 5 | AgentManager 集成守卫 | agent/router/agent_manager.py |
| 6 | Schemas 更新 | schemas/agent_ops.py |
| 7 | Repositories 增强 | repositories/agent_ops_repo.py |
| 8 | Service 改造 | services/agent_ops_service.py |
| 9 | API 端点新增 | api/v1/agent_ops.py |
| 10 | 前端类型+API+Store | types/agent-ops.types.ts, api/agent-ops.api.ts, stores/agent-ops.store.ts |
| 11 | 前端路由菜单收敛 | router/routes/ops.routes.ts, composables/useMenu.ts |
| 12 | 前端 AgentManageView 大改 | views/ops/AgentManageView.vue |

---

## 7. 验收标准

- 4个核心Agent显示为"已接入"、"参与路由=是"，可暂停/恢复路由
- 5个规划Agent显示为"规划中/仅展示"，route_enabled=false
- 点击暂停路由后 AgentManager 真实阻止该 Agent 接收新请求
- 点击恢复路由后 Agent 可重新接收请求
- 暂停/恢复操作写入 agent_runtime_events 表
- 定义Tab：分组展示、详情抽屉、状态标签正确
- 运行态Tab：操作确认弹窗、审计日志可查
- 拓扑Tab：设计/运行拓扑可切换、节点颜色按状态区分
- 菜单中无占位入口
