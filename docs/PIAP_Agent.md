# PIAP Agent 管理页面产品化改造方案

> 角色视角：产品经理 / AgentOps 产品负责人  
> 目标页面：`/ops/agents`  
> 页面原则：**只保留一个 Agent 管理页面，页面内部保持三个模块：定义 / 运行态 / 拓扑**  
> 目标用户：应用开发者、平台运维员、系统管理员  
> 版本建议：Agent 管理中心 v1.0

---

## 1. 产品定位

当前 Agent 管理页已经具备正确雏形：一个页面内包含 **定义、运行态、拓扑** 三个模块。后续不建议再拆成多个独立页面，而应将它升级为真正的 **Agent 控制中心**。

目标是让客户打开页面后能清楚回答：

1. 系统里有哪些 Agent？
2. 哪些 Agent 已经真实接入？
3. 哪些 Agent 只是规划中？
4. 哪些 Agent 是历史遗留？
5. 当前 Agent 是否真的在运行？
6. 点击停止后是否真的影响请求？
7. 请求在多 Agent 系统中如何流转？
8. 出问题时应该从哪里排查？

最终产品目标：

> 让客户相信 PIAP 的多 Agent 系统是可理解、可控制、可追踪、可维护的。

---

## 2. 必须保持的页面要求

根据当前要求，页面结构保持不变：

```text
/ops/agents
└── Agent 管理
    ├── 定义
    ├── 运行态
    └── 拓扑
```

不建议再单独拆出：

- Agent 拓扑图
- 路由策略
- 流程节点
- 工具注册
- 发布管理

这些内容可以在 Agent 管理页内部逐步吸收，避免左侧菜单出现大量“开发中”入口，让客户误以为系统不完整。

建议左侧菜单收敛为：

```text
Agent 管理
Prompt 管理
RAG 配置
个人设置
```

---

## 3. 当前页面主要问题

### 3.1 状态不够真实

当前页面中部分 Agent 显示为 `running`，但执行次数为 0。客户会自然理解为“正在运行”，但实际上这些 Agent 可能只是数据库里的历史记录或静态注册项。

这会造成信任问题：

```text
页面显示 running
但 Agent 实际没有参与路由，也没有承担业务功能
```

### 3.2 历史 Agent、规划 Agent、核心 Agent 混在一起

当前列表中可能出现：

- Quality Chat
- Agent Manager
- Inspection Task Agent
- Quality Judgement
- Lab Detection
- Market Monitor
- Legacy Quality
- LLM-native Quality
- Shared Memory Hierarchy

其中前几项属于当前核心链路；中间部分更像规划中专业 Agent；最后几项更像历史遗留。  
如果全部平铺展示，客户难以判断哪些是真的可用能力。

### 3.3 停止按钮可能只是展示状态

如果点击“停止”只是修改数据库里的 `runtime.status`，而后端执行入口 `AgentManager` 没有检查该状态，那么请求仍可能继续进入该 Agent。

这会导致：

```text
客户点击停止
页面显示 stopped
但业务请求仍然进入 Agent
```

这是 Agent 管理页最需要优先修复的问题。

### 3.4 拓扑图不是实时运行拓扑

当前拓扑更接近“设计拓扑”或“注册拓扑”，它能展示系统规划结构，但不一定能说明某次请求真实经过了哪些 Agent。

需要明确区分：

- 设计拓扑：系统规划结构
- 运行拓扑：当前真实启用的 Agent 链路
- 调用链路：某次请求实际经过的节点和耗时

---

## 4. 建议确定的多 Agent 框架

建议系统最终按如下形态表达：

```text
用户请求
  ↓
Agent Manager：统一入口与路由决策
  ↓
Route Policy：判断请求类型、附件类型、任务意图、RAG 意图
  ├── Quality Chat：普通聊天、RAG 问答、轻量知识问答
  ├── Inspection Task Agent：正式检测任务、图片检测、文件检测、结果落库
  ├── Quality Judgement：统一质量判定、质检问答、证据合成、判定门控
  ├── Memory Manager：共享记忆读取、写入、污染检测、回滚治理
  ├── Lab Detection：实验室检测指标解析
  ├── Supervision Sampling：抽检计划、样品管理、现场检查记录
  ├── Market Monitor：市场价格、销量、渠道异常
  ├── Public Opinion：投诉、新闻、社媒舆情分析
  └── Trend Evolution：风险趋势推演、情景预测
```

但页面上必须明确区分 Agent 类型，不能让所有 Agent 都显示为同等可用。

推荐分组：

| 分组 | Agent | 产品状态 | 客户解释 |
|---|---|---|---|
| 核心运行链路 | Agent Manager | 已接入 | 统一请求入口，负责路由分发 |
| 核心运行链路 | Quality Chat | 已接入 | 轻量问答、RAG 问答入口 |
| 核心运行链路 | Inspection Task Agent | 已接入 | 正式检测任务创建、执行、结果落库 |
| 核心运行链路 | Quality Judgement | 已接入 | 统一质量判定与质检问答 |
| 记忆治理能力 | Memory Manager | 部分接入 | 共享记忆、污染传播、回滚治理 |
| 专业规划 Agent | Lab Detection | 规划中 | 样品检测和标准指标比对 |
| 专业规划 Agent | Supervision Sampling | 规划中 | 抽检计划与现场检查 |
| 专业规划 Agent | Market Monitor | 规划中 | 市场异常与渠道监测 |
| 专业规划 Agent | Public Opinion | 规划中 | 舆情、投诉与新闻分析 |
| 专业规划 Agent | Trend Evolution | 规划中 | 风险趋势推演 |
| 历史兼容 Agent | Legacy Quality | 已废弃 | 旧版质量流程，不参与主路由 |
| 历史兼容 Agent | LLM-native Quality | 已合并 | 已合入 Quality Judgement |
| 历史兼容 Agent | Shared Memory Hierarchy | 已替换 | 旧版共享记忆层级命名，应迁移为 Memory Manager |

---

## 5. 模块一：定义

### 5.1 模块目标

定义模块负责回答：

```text
系统中有哪些 Agent？
每个 Agent 负责什么？
哪些已经接入主流程？
哪些只是规划中？
哪些是历史兼容？
哪些参与路由？
```

### 5.2 推荐页面结构

定义模块建议包含：

1. 顶部概览卡片
2. 筛选区
3. 分组 Agent 列表
4. Agent 详情抽屉

### 5.3 顶部概览卡片

建议增加：

| 卡片 | 含义 |
|---|---|
| 核心 Agent | 当前真实接入主流程的 Agent 数量 |
| 规划中 Agent | 已注册但未接入业务链路的 Agent 数量 |
| 历史 Agent | 保留但不参与路由的 Agent 数量 |
| 可控制 Agent | 支持启停或暂停路由的 Agent 数量 |
| 异常 Agent | 最近失败率或错误率超阈值的 Agent 数量 |

示例：

```text
核心 Agent：4
规划中 Agent：5
历史 Agent：3
可控制 Agent：4
异常 Agent：0
```

### 5.4 表格字段建议

| 字段 | 说明 |
|---|---|
| 名称 | Agent 名称 |
| 类型 | 核心 / 记忆治理 / 规划中 / 历史 |
| 能力说明 | 面向客户的自然语言说明 |
| 子图 Key | 技术标识 |
| 入口图 | 技术入口 |
| 工作流绑定 | 运行绑定关系 |
| 版本 | 当前版本 |
| 接入状态 | 已接入 / 部分接入 / 规划中 / 已废弃 |
| 参与路由 | 是 / 否 |
| 运行态 | running / stopped / degraded / maintenance |
| 最近执行 | 最近一次真实调用时间 |
| 指标 | 执行数、成功率、平均延迟 |

### 5.5 状态标签建议

产品接入状态：

| 状态 | 含义 |
|---|---|
| 已接入 | 参与当前主流程 |
| 部分接入 | 有部分后端能力，但未完整闭环 |
| 规划中 | 已注册展示，但暂不执行业务 |
| 历史兼容 | 旧版保留，不建议使用 |
| 已废弃 | 不参与路由，等待清理 |

运行状态：

| 状态 | 含义 |
|---|---|
| running | 当前允许执行 |
| stopped | 已停止，不允许执行 |
| degraded | 降级运行 |
| maintenance | 维护模式 |
| readonly | 仅展示，不支持控制 |

### 5.6 Agent 详情抽屉

点击 Agent 后展示：

```text
基础信息：
- 名称
- 类型
- 子图 Key
- 入口图
- 工作流绑定
- 版本

能力说明：
- 负责什么
- 适用场景
- 不适用场景

路由信息：
- 是否参与主路由
- 命中规则
- 上游 Agent
- 下游 Agent

绑定资源：
- Prompt 版本
- 工具列表
- RAG 空间或知识源
- 模型配置

运行指标：
- 今日执行次数
- 累计执行次数
- 成功率
- 平均延迟
- Token 消耗
- 最近失败原因

操作记录：
- 最近修改人
- 修改内容
- 修改时间
```

---

## 6. 模块二：运行态

### 6.1 模块目标

运行态模块负责回答：

```text
哪些 Agent 正在运行？
哪些 Agent 可以暂停？
暂停后是否真的生效？
最近有没有失败？
执行延迟是否异常？
系统当前是否健康？
```

### 6.2 运行态顶部卡片

建议展示：

| 卡片 | 含义 |
|---|---|
| 运行中 Agent | 当前允许执行的 Agent 数量 |
| 已暂停 Agent | 当前暂停的 Agent 数量 |
| 今日执行 | 今日所有 Agent 执行次数 |
| 成功率 | 当前 Agent 体系总体成功率 |
| 平均延迟 | 当前 Agent 体系平均响应耗时 |
| 最近错误 | 最近 1 小时错误数 |

### 6.3 运行态表格字段

| 字段 | 说明 |
|---|---|
| Agent | Agent 名称 |
| 类型 | 核心 / 规划中 / 历史 |
| 子图 | subgraph_key |
| 参与路由 | 是 / 否 |
| 状态 | running / stopped / degraded / maintenance |
| 执行数 | 累计执行次数 |
| 今日执行 | 今日执行次数 |
| 成功率 | 成功执行比例 |
| 平均延迟 | 平均执行耗时 |
| P95 延迟 | 更真实的性能指标 |
| 最近执行 | 最近一次真实调用时间 |
| 最近错误 | 最近一次错误摘要 |
| 操作 | 暂停路由 / 恢复路由 / 维护模式 / 查看日志 |

### 6.4 “停止”按钮的产品定义

不建议只使用“停止”。  
建议分成两个更准确的能力：

#### 暂停路由

含义：

```text
该 Agent 不再接收新请求。
已在执行中的请求不强制中断。
```

#### 停止运行单元

含义：

```text
该 Agent 运行单元进入 stopped。
新请求不允许进入。
必要时可以中止后台任务。
```

页面操作建议：

```text
暂停路由
恢复路由
进入维护
查看日志
```

对规划中 Agent 显示：

```text
仅展示
```

对历史 Agent 显示：

```text
已废弃
```

### 6.5 操作确认弹窗

点击暂停时，需要提示影响范围：

```text
你正在暂停 Quality Chat。

影响：
- 普通聊天请求将无法进入 Quality Chat。
- RAG 问答可能受影响。
- 已在执行中的请求不会被中断。
- 系统可按配置 fallback 到其他 Agent 或返回不可用提示。

请输入暂停原因：
[________________]

确认暂停 / 取消
```

### 6.6 运行态闭环

后端必须形成闭环：

```text
用户点击暂停
  ↓
前端调用暂停接口
  ↓
后端写入 route_enabled = false
  ↓
AgentManager 路由前检查 route_enabled
  ↓
如果目标 Agent 不可用：
    - 阻止执行
    - 返回明确提示
    - 或 fallback
  ↓
记录审计日志
  ↓
前端显示状态变更
```

---

## 7. 模块三：拓扑

### 7.1 模块目标

拓扑模块负责回答：

```text
请求从哪里进入？
经过哪些 Agent？
每个 Agent 负责哪个节点？
哪个节点最近有问题？
当前看到的是设计结构还是真实调用链路？
```

### 7.2 三种拓扑视图

建议在拓扑 Tab 内增加二级切换：

```text
设计拓扑 / 运行拓扑 / 调用链路
```

#### 设计拓扑

展示系统规划结构，适合售前、培训、解释系统架构。

#### 运行拓扑

只展示当前真实启用、参与路由的 Agent。

#### 调用链路

选择一次请求 Trace 后，展示真实经过的节点：

```text
用户请求
  ↓
Agent Manager
  ↓
Route Policy
  ↓
Quality Chat
  ↓
RAG Retrieval
  ↓
Answer Synthesis
```

每条边显示耗时，每个节点显示状态。

### 7.3 拓扑节点颜色

| 节点状态 | 颜色建议 |
|---|---|
| 已接入运行 | 绿色 |
| 当前调用路径 | 蓝色高亮 |
| 部分接入 | 黄色 |
| 规划中 | 灰色 |
| 历史兼容 | 橙色 |
| 错误 / 不可用 | 红色 |

### 7.4 拓扑交互能力

建议支持：

- 点击节点打开详情
- 高亮最近一次调用路径
- 展示节点调用次数
- 展示节点平均耗时
- 展示节点错误率
- 隐藏/显示规划 Agent
- 隐藏/显示历史 Agent
- 根据 Agent 类型筛选
- 根据运行状态筛选

---

## 8. 前端修改建议

### 8.1 主要文件

```text
frontend/src/views/ops/AgentManageView.vue
frontend/src/stores/agent-ops.store.ts
frontend/src/api/agent-ops.api.ts
frontend/src/types/agent-ops.types.ts
frontend/src/composables/useMenu.ts
```

### 8.2 AgentManageView.vue

保持三个 Tab：

```vue
<el-tabs v-model="activeTab">
  <el-tab-pane label="定义" name="definitions" />
  <el-tab-pane label="运行态" name="runtime" />
  <el-tab-pane label="拓扑" name="topology" />
</el-tabs>
```

增强内容：

| 模块 | 修改 |
|---|---|
| 定义 | 增加分组展示、状态标签、详情抽屉 |
| 运行态 | 增加暂停路由、恢复路由、维护模式、操作确认 |
| 拓扑 | 增加设计拓扑/运行拓扑/调用链路切换 |

### 8.3 useMenu.ts

建议隐藏独立占位菜单，保留一个 Agent 管理入口。

保留：

```text
Agent 管理 -> /ops/agents
```

隐藏或合并：

```text
Agent 拓扑图
流程节点
工具注册
发布管理
```

### 8.4 前端新增类型

```ts
export type AgentLifecycleStatus =
  | "active"
  | "partial"
  | "planned"
  | "legacy"
  | "deprecated";

export type AgentRuntimeStatus =
  | "running"
  | "stopped"
  | "degraded"
  | "maintenance"
  | "readonly";

export interface AgentDefinition {
  id: string;
  name: string;
  description: string;
  subgraph_key: string;
  entry_graph: string;
  workflow_binding: string;
  graph_version: string;
  lifecycle_status: AgentLifecycleStatus;
  runtime_status: AgentRuntimeStatus;
  route_enabled: boolean;
  supports_start_stop: boolean;
  supports_route_toggle: boolean;
  group: "core" | "memory" | "planned" | "legacy";
  customer_visible_description: string;
}
```

---

## 9. 后端服务修改建议

### 9.1 主要文件

```text
backend/agent/topology_catalog.py
backend/agent/router/agent_manager.py
backend/app/services/agent_ops_service.py
backend/app/repositories/agent_ops_repo.py
backend/app/api/v1/agent_ops.py
backend/app/models/agent_ops.py
backend/app/schemas/agent_ops.py
```

### 9.2 topology_catalog.py

建议为每个 Agent 增加：

```python
{
    "lifecycle_status": "active",
    "group": "core",
    "route_enabled_default": True,
    "customer_visible_description": "用于普通问答、RAG 问答和轻量质检解释。"
}
```

规划中 Agent：

```python
{
    "lifecycle_status": "planned",
    "group": "planned",
    "route_enabled_default": False
}
```

历史 Agent：

```python
{
    "lifecycle_status": "legacy",
    "group": "legacy",
    "route_enabled_default": False
}
```

### 9.3 agent_ops_service.py

同步 Agent 时应处理旧数据：

```text
如果数据库存在但 catalog 不存在：
  lifecycle_status = deprecated
  route_enabled = false
  is_active = false
  runtime_status = stopped
```

这样可以解决旧 Agent 仍显示 running 的问题。

### 9.4 agent_manager.py

必须在执行前检查运行态：

```python
decision = self._route_policy.decide(router_input)

runtime = await AgentRuntimeGuard.check(
    org_id=request.org_id,
    selected_agent=decision.selected_agent,
    sub_route=decision.sub_route,
)

if not runtime.allowed:
    return AgentRouterOutput(
        route_decision=decision,
        status="blocked",
        degrade_reason=runtime.reason,
        agent_output={
            "message_type": "agent_unavailable",
            "answer": runtime.customer_message,
        },
    )
```

建议新增 `AgentRuntimeGuard`，避免 `AgentManager` 直接耦合数据库。

---

## 10. 数据库是否需要变更

结论：**建议需要小幅数据库变更。**

如果只是美化前端，可以不改数据库。  
但如果要实现“停止有效、状态真实、客户可信”，数据库必须补字段。

### 10.1 agent_definitions 表建议新增字段

| 字段 | 类型 | 必要性 | 说明 |
|---|---|---|---|
| lifecycle_status | varchar | 必须 | active / partial / planned / legacy / deprecated |
| group_key | varchar | 必须 | core / memory / planned / legacy |
| route_enabled | boolean | 必须 | 是否参与路由 |
| supports_route_toggle | boolean | 建议 | 是否允许暂停/恢复路由 |
| customer_visible_description | text | 建议 | 给客户看的描述 |
| deprecated_reason | text | 可选 | 废弃原因 |
| replaced_by_agent_id | varchar | 可选 | 被哪个新 Agent 替代 |

### 10.2 agent_runtime_instances 表建议新增字段

| 字段 | 类型 | 必要性 | 说明 |
|---|---|---|---|
| runtime_status | varchar | 建议 | running / stopped / degraded / maintenance |
| last_health_check_at | datetime | 建议 | 最近健康检查 |
| last_error_message | text | 建议 | 最近错误 |
| last_error_at | datetime | 建议 | 最近错误时间 |
| maintenance_reason | text | 可选 | 维护原因 |
| updated_by | varchar | 建议 | 最近操作人 |

### 10.3 新增 agent_runtime_events 表

用于记录运行态操作：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| org_id | uuid | 组织 |
| agent_id | uuid | Agent |
| runtime_key | varchar | 运行单元 |
| event_type | varchar | pause_route / resume_route / start / stop / maintenance |
| before_status | varchar | 变更前状态 |
| after_status | varchar | 变更后状态 |
| reason | text | 操作原因 |
| operator_id | uuid | 操作人 |
| created_at | datetime | 创建时间 |

### 10.4 增强 agent_route_logs

字段建议：

| 字段 | 类型 | 说明 |
|---|---|---|
| trace_id | varchar | Trace |
| selected_agent | varchar | 选中的 Agent |
| selected_sub_route | varchar | 子路由 |
| route_source | varchar | rule / model / manual |
| reason | text | 路由原因 |
| blocked | boolean | 是否被运行态阻止 |
| blocked_reason | text | 阻止原因 |
| fallback_agent | varchar | fallback Agent |

---

## 11. API 设计建议

### 11.1 Agent 列表

```http
GET /v1/agent-ops/agents
```

返回应包含：

```json
{
  "id": "xxx",
  "name": "Quality Chat",
  "subgraph_key": "chat",
  "group": "core",
  "lifecycle_status": "active",
  "runtime_status": "running",
  "route_enabled": true,
  "supports_start_stop": true,
  "supports_route_toggle": true,
  "customer_visible_description": "用于普通问答、RAG 问答和轻量质检解释。"
}
```

### 11.2 暂停路由

```http
POST /v1/agent-ops/runtime/agents/{runtime_key}/pause-route
```

请求：

```json
{
  "reason": "临时维护 RAG 问答链路"
}
```

### 11.3 恢复路由

```http
POST /v1/agent-ops/runtime/agents/{runtime_key}/resume-route
```

### 11.4 运行拓扑

```http
GET /v1/agent-ops/agents/topology?mode=runtime
```

参数：

| 参数 | 说明 |
|---|---|
| mode=design | 设计拓扑 |
| mode=runtime | 当前运行拓扑 |
| mode=trace | 某次调用链路 |
| trace_id | mode=trace 时使用 |
| include_planned | 是否展示规划中 Agent |
| include_legacy | 是否展示历史 Agent |

---

## 12. 优先级规划

### P0：必须先做

1. 保留 `/ops/agents` 单页面三 Tab。
2. 清理旧 Agent 展示，不再让历史 Agent 显示为正常 running。
3. 增加 lifecycle_status、group、route_enabled。
4. 修复停止或暂停操作，让它真实影响路由。
5. AgentManager 执行前检查运行态。
6. 规划中 Agent 显示为“规划中 / 仅展示”。

### P1：提升体验

1. Agent 分组展示。
2. Agent 详情抽屉。
3. 操作确认弹窗。
4. 运行态审计日志。
5. 拓扑图区分设计拓扑和运行拓扑。
6. 节点点击详情。
7. 最近路由日志。

### P2：完整 AgentOps

1. Trace 调用链路拓扑。
2. Agent 版本管理。
3. Prompt 绑定展示。
4. 工具绑定展示。
5. RAG 绑定展示。
6. 灰度发布。
7. 一键回滚。
8. 健康检查和告警。

---

## 13. 验收标准

### 页面结构

- 只保留一个 Agent 管理主页面 `/ops/agents`。
- 页面内保持三个 Tab：定义 / 运行态 / 拓扑。
- Agent 相关能力不再分散到多个占位页面。

### 定义模块

- Agent 能按核心、记忆治理、规划中、历史分组。
- 旧 Agent 不再显示为正常 running。
- 每个 Agent 有客户可理解的能力说明。
- 能看到是否参与路由。
- 能打开详情抽屉。

### 运行态模块

- 点击暂停路由后，该 Agent 不再接收新请求。
- 点击恢复路由后，该 Agent 可以重新接收请求。
- 停止或暂停操作写入事件日志。
- 规划中 Agent 显示为“仅展示”。
- 历史 Agent 显示为“已废弃”或“兼容保留”。

### 拓扑模块

- 默认展示核心运行链路。
- 可切换设计拓扑和运行拓扑。
- 可隐藏或显示规划中 Agent。
- 可隐藏或显示历史 Agent。
- 点击节点可查看详情。
- 节点显示状态、执行次数、平均延迟。

### 后端

- AgentManager 执行前检查 runtime_status 和 route_enabled。
- route_enabled=false 时不会进入对应 Agent。
- 旧 Agent 自动标记为 legacy 或 deprecated。
- 所有状态变更有事件记录。
- API 返回字段足够支撑前端展示。

### 数据库

- Agent 定义表支持生命周期、分组、路由字段。
- Runtime 表支持真实运行状态和维护信息。
- Runtime 事件表记录启停和暂停路由。
- 路由日志可支持后续调用链路分析。

---

## 14. 最终产品效果

改造后，客户打开 Agent 管理页会看到：

```text
定义：系统有哪些 Agent，它们分别负责什么，哪些已接入，哪些规划中。
运行态：哪些 Agent 真的在运行，是否健康，能否暂停，暂停是否生效。
拓扑：请求如何在 Agent 之间流动，哪里是核心链路，哪里是规划能力。
```

最终页面不是“列出很多 Agent”，而是成为客户可理解、可控制、可诊断的 **Agent 控制中心**。

一句话总结：

> 在保持一个页面和三个模块不变的前提下，把 Agent 管理从展示型页面升级为真实可信的 AgentOps 控制台。
