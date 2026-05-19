# PIAP 路由策略页面展示与监控优化方案（非配置版）

> 角色视角：产品经理 / AgentOps 产品负责人  
> 目标页面：`/ops/agents/intent-routes` 或合并到 `Agent 管理 > 路由策略`  
> 核心目标：**先不做路由策略配置与发布，只把当前真实路由逻辑清晰展示、可模拟、可观测、可诊断**  
> 适用角色：应用开发者、平台运维员、系统管理员  
> 建议版本：Routing Strategy Viewer v1.0

---

## 1. 本版边界说明

本版不实现：

- 新增路由规则
- 编辑路由规则
- 删除路由规则
- 调整规则优先级
- 发布策略版本
- 灰度发布
- 策略回滚
- 自然语言生成路由策略
- 数据库动态路由配置

本版只实现：

- 展示当前系统真实路由策略
- 展示 Agent Manager 如何把请求路由到目标 Agent
- 展示目标 Agent 内部子路由
- 展示当前硬编码规则的优先级
- 展示最近真实路由事件
- 展示每条规则的命中情况
- 提供路由模拟器，但模拟器只用于解释当前策略，不修改策略
- 优化页面布局和路由图，让客户能看懂

一句话：

> 先把“当前系统到底怎么路由”讲清楚，不急着开放“让用户配置路由”。

---

## 2. 当前项目真实路由策略

当前项目中，真实运行时路由主要由 `AgentManager` 和 `AgentRoutePolicy` 完成。

当前真实一级路由结构应展示为：

```text
Agent Manager
  ├── Quality Chat
  │   ├── general_chat
  │   └── rag_qa
  │
  └── Inspection Task Agent
      ├── task_create
      ├── inspection_execute
      └── quality_qa
```

当前不应把页面重点展示成：

```text
quality_judgement / legacy_quality / llm_native_quality
```

因为这容易让客户误以为真实运行时就是这些旧概念在承担路由。

---

## 3. 当前真实路由规则

当前应按以下规则展示：

| 优先级 | 命中条件 | 目标 Agent | 子路由 | 说明 |
|---|---|---|---|---|
| P0 | 前端强制 `force_agent=inspection_task` | Inspection Task Agent | 指定子路由或 `task_create` | 手动覆盖 |
| P0 | 前端强制 `force_agent=chat` | Quality Chat | 指定子路由或 `general_chat` | 手动覆盖 |
| P1 | 结构化文件 + 检测/质检意图 | Inspection Task Agent | `inspection_execute` | 文件检测 |
| P2 | 图片 + 检测/质检意图 | Inspection Task Agent | `inspection_execute` | 图片检测 |
| P3 | 明确创建任务意图 | Inspection Task Agent | `task_create` | 创建检测任务 |
| P4 | 质量、质检、缺陷、合格、标准等问答语义 | Inspection Task Agent | `quality_qa` | 质检问答 |
| P5 | 选中 RAG 空间或知识库问答意图 | Quality Chat | `rag_qa` | RAG 问答 |
| P6 | 短句、代词、泛化表达等模糊输入 | Quality Chat | `general_chat` | 可尝试模型分类兜底 |
| P7 | 其他默认请求 | Quality Chat | `general_chat` | 普通聊天 |

---

## 4. 当前页面主要问题

### 4.1 页面文字太多

当前页面更像说明文档，而不是产品界面。客户需要读大量文字才能理解当前路由模式、默认路由、规则优先级和命中原因。

页面应减少大段文字，更多使用：

- 流程图
- 规则卡片
- 路由树
- 命中路径
- 最近事件
- 指标卡片

### 4.2 图形表达不清楚

当前曲线图不适合表达路由逻辑，问题包括：

- 节点位置不稳定
- 曲线交叉
- 先后顺序不清楚
- 条件、规则、目标 Agent 混在一起
- 看不出请求从哪里进入、经过什么判断、最后去了哪里

路由图应该表达的是：

```text
请求 → Agent Manager → 信号识别 → 规则匹配 → 目标 Agent → 子路由
```

而不是一张自由散布的网络图。

### 4.3 页面展示与真实代码容易不一致

当前页面如果继续突出 `quality_judgement`，但真实运行时主要路由到 `chat` 和 `inspection_task`，就会导致客户误解。

本版页面必须以真实运行结构为准：

```text
chat
inspection_task
```

如果未来 `quality_judgement` 真正作为独立运行 Agent 接入，再在页面中显示。

---

## 5. 页面产品定位

本版页面定位为：

> **Agent 路由策略查看与诊断中心。**

它不负责配置策略，而负责让客户清楚知道：

1. 当前系统的路由规则是什么。
2. 请求会被路由到哪个 Agent。
3. 目标 Agent 内部会进入哪个子路由。
4. 最近真实请求命中了哪些规则。
5. 某次请求为什么这么路由。
6. 页面展示内容和真实系统运行保持一致。

---

## 6. 推荐页面结构

建议页面改成以下结构：

```text
路由策略
├── 顶部状态区
│   ├── 路由模式
│   ├── 默认目标
│   ├── 当前规则数
│   ├── 最近 24h 路由次数
│   ├── 当前参与路由 Agent
│   └── 异常路由次数
│
├── 主工作区
│   ├── 左侧：Agent 路由树
│   ├── 中间：横向路由决策流图
│   └── 右侧：选中规则/节点详情
│
├── 当前规则表
│   ├── 优先级
│   ├── 命中条件
│   ├── 目标 Agent
│   ├── 子路由
│   ├── 命中次数
│   ├── 平均延迟
│   └── 最近命中时间
│
├── 路由模拟器
│   ├── 输入文本
│   ├── 附件类型
│   ├── 是否选择 RAG 空间
│   └── 模拟路由结果
│
└── 最近路由事件
    ├── 时间
    ├── 请求摘要
    ├── 命中规则
    ├── 目标 Agent
    ├── 子路由
    └── 路由原因
```

---

## 7. 顶部状态区设计

顶部状态区应回答“当前路由系统是否清晰可用”。

推荐指标卡：

| 卡片 | 展示内容 | 价值 |
|---|---|---|
| 路由模式 | `规则优先 + 模型兜底` | 告诉客户系统如何决策 |
| 默认目标 | `Quality Chat / general_chat` | 告诉客户未命中规则时去哪 |
| 当前规则数 | `8 条内置规则` | 告诉客户当前规则规模 |
| 参与 Agent | `2 个` | 告诉客户真实参与路由的 Agent 数 |
| 最近 24h 路由 | `1253 次` | 告诉客户是否有真实流量 |
| 异常路由 | `0 次` | 告诉客户是否健康 |

示例：

```text
路由模式：规则优先，模型兜底
默认目标：Quality Chat / general_chat
当前规则：8 条内置规则
参与 Agent：2 个
最近 24h 路由：1253 次
异常路由：0 次
```

---

## 8. 核心图形区域优化

### 8.1 使用横向决策流图

替换当前自由曲线图，改为横向固定层级图：

```text
[用户请求]
    →
[Agent Manager]
    →
[信号识别]
    →
[规则匹配]
    →
[目标 Agent]
    →
[Agent 子路由]
```

### 8.2 当前项目推荐图形

```text
用户请求
  ↓
Agent Manager
  ↓
信号识别
  ├── 是否有图片
  ├── 是否有结构化文件
  ├── 是否有任务创建意图
  ├── 是否有质量问答语义
  ├── 是否选择 RAG 空间
  └── 是否是模糊输入
  ↓
规则匹配
  ├── P1：结构化文件 + 检测意图
  ├── P2：图片 + 检测意图
  ├── P3：创建任务
  ├── P4：质检问答
  ├── P5：RAG 问答
  ├── P6：模糊输入
  └── P7：默认聊天
  ↓
目标 Agent
  ├── Quality Chat
  └── Inspection Task Agent
  ↓
子路由
  ├── general_chat
  ├── rag_qa
  ├── task_create
  ├── inspection_execute
  └── quality_qa
```

### 8.3 连线规则

| 连线类型 | 含义 |
|---|---|
| 实线 | 当前主路由逻辑 |
| 虚线 | 模型兜底或 fallback |
| 蓝色高亮 | 最近一次命中路径 |
| 绿色 | 当前正常路径 |
| 灰色 | 未命中路径 |
| 红色 | 异常路径 |

---

## 9. Agent 路由树

左侧建议展示 Agent 路由树，让客户快速理解系统结构。

```text
Agent Manager
├── Quality Chat
│   ├── general_chat：普通聊天
│   └── rag_qa：知识库问答
│
└── Inspection Task Agent
    ├── task_create：创建检测任务
    ├── inspection_execute：图片/文件检测执行
    └── quality_qa：质量标准/缺陷问答
```

点击树节点后，中间图高亮对应链路，右侧展示说明。

---

## 10. 当前规则表

规则表只展示当前系统内置规则，不提供新增、编辑、删除功能。

### 10.1 推荐字段

| 字段 | 示例 |
|---|---|
| 优先级 | P1 |
| 规则名称 | 图片检测意图 |
| 条件摘要 | 图片附件 + 检测/质检意图 |
| 目标 Agent | Inspection Task Agent |
| 子路由 | inspection_execute |
| 路由来源 | 内置规则 |
| 最近 24h 命中 | 231 |
| 平均延迟 | 42 ms |
| 最近命中 | 2026-05-19 14:30 |
| 操作 | 查看详情 / 模拟 |

### 10.2 规则详情抽屉

点击“查看详情”后显示：

```text
规则名称：图片检测意图
优先级：P2
目标 Agent：Inspection Task Agent
目标子路由：inspection_execute
触发条件：
- 请求包含图片附件
- 文本中包含检测、质检、合格、不合格等意图
说明：
- 用于图片质检任务
- 命中后进入正式检测执行链路
最近命中：
- 最近 24h 命中次数
- 最近一次命中时间
- 最近一次请求摘要
```

---

## 11. 路由模拟器

### 11.1 模拟器定位

模拟器只用于解释当前策略，不修改策略。

它回答：

```text
如果用户输入这句话，并带这些附件，系统会路由到哪里？
为什么？
```

### 11.2 输入项

| 输入项 | 示例 |
|---|---|
| 用户文本 | “帮我检测这张图片是否合格” |
| 附件类型 | 图片 / Excel / PDF / 无 |
| 是否选择 RAG 空间 | 是 / 否 |
| 请求类型 | chat / task |
| 是否有图片 URL | 是 / 否 |

### 11.3 输出项

```text
命中规则：P2 图片 + 检测意图
目标 Agent：Inspection Task Agent
子路由：inspection_execute
路由来源：内置规则
原因：请求包含图片附件，同时文本中出现“检测”“合格”等质检意图词。
```

同时中间图高亮路径：

```text
用户请求 → Agent Manager → 图片信号 → P2 → Inspection Task Agent → inspection_execute
```

### 11.4 模拟器价值

它能让客户快速确认：

- 图片检测会不会进入检测 Agent
- RAG 问答会不会进入知识库问答
- 普通聊天会不会进入聊天 Agent
- 模糊输入是否会触发模型分类兜底

---

## 12. 最近路由事件

页面底部展示最近真实路由事件。

### 12.1 字段

| 字段 | 说明 |
|---|---|
| 时间 | 路由发生时间 |
| 请求摘要 | 用户输入前若干字 |
| 命中规则 | P1/P2/P3 等 |
| 目标 Agent | Quality Chat / Inspection Task Agent |
| 子路由 | general_chat / rag_qa / task_create 等 |
| 路由来源 | rule / manual / model_classifier |
| 原因 | 命中原因 |
| 耗时 | 路由判断耗时 |
| 状态 | 成功 / 失败 |

### 12.2 用途

最近路由事件能证明页面展示不是静态文案，而是和真实请求有关。

---

## 13. 前端修改建议

### 13.1 主要文件

```text
frontend/src/views/ops/IntentRouteView.vue
frontend/src/stores/agent-ops.store.ts
frontend/src/api/agent-ops.api.ts
frontend/src/types/agent-ops.types.ts
frontend/src/views/ops/intent-route-fallback.ts
```

如果路由策略合并到 Agent 管理页面，也需要修改：

```text
frontend/src/views/ops/AgentManageView.vue
```

### 13.2 页面组件拆分建议

建议重构为：

```text
RoutePolicyViewer.vue
├── RoutePolicyHeader.vue
├── RouteMetricCards.vue
├── AgentRouteTree.vue
├── RouteDecisionFlow.vue
├── BuiltInRuleTable.vue
├── BuiltInRuleDrawer.vue
├── RouteSimulator.vue
└── RouteEventTimeline.vue
```

### 13.3 图形组件建议

继续使用 ECharts 也可以，但不要用力导向图。

推荐使用固定布局 graph：

```ts
series: [{
  type: "graph",
  layout: "none",
  edgeSymbol: ["none", "arrow"],
  data: fixedLayerNodes,
  links: decisionEdges
}]
```

节点分层：

```text
第 1 层：用户请求
第 2 层：Agent Manager
第 3 层：信号识别
第 4 层：规则
第 5 层：目标 Agent
第 6 层：子路由
```

---

## 14. 后端修改建议

本版不需要数据库可配置策略，但需要后端提供“当前策略展示、模拟、日志”能力。

### 14.1 推荐新增服务

```text
RouteSignalBuilder
RoutePolicyViewService
RouteSimulationService
RouteEventService
```

### 14.2 RouteSignalBuilder

负责从请求中提取标准信号：

```json
{
  "has_image": true,
  "has_structured_file": false,
  "has_task_intent": true,
  "has_quality_signal": true,
  "has_rag_space": false,
  "has_rag_signal": false,
  "is_ambiguous": false
}
```

这些信号可以复用当前 `route_policy.py` 中已有判断。

### 14.3 RoutePolicyViewService

负责把当前硬编码规则转换成前端可展示结构。

输出示例：

```json
{
  "mode": "rule_first_with_model_fallback",
  "default_target": {
    "agent": "chat",
    "sub_route": "general_chat"
  },
  "agents": [
    {
      "key": "chat",
      "label": "Quality Chat",
      "sub_routes": ["general_chat", "rag_qa"]
    },
    {
      "key": "inspection_task",
      "label": "Inspection Task Agent",
      "sub_routes": ["task_create", "inspection_execute", "quality_qa"]
    }
  ],
  "rules": [
    {
      "priority": 20,
      "name": "图片检测意图",
      "target_agent": "inspection_task",
      "target_sub_route": "inspection_execute"
    }
  ]
}
```

### 14.4 RouteSimulationService

负责调用当前真实 `AgentRoutePolicy.decide()`，返回模拟结果。

注意：模拟器不能执行真实 Agent，只返回路由决策。

### 14.5 RouteEventService

负责读取 `agent_route_logs`，展示最近真实路由事件。

---

## 15. API 设计建议

### 15.1 获取当前路由策略视图

```http
GET /v1/agent-ops/routing/current
```

返回：

```json
{
  "mode": "rule_first_with_model_fallback",
  "default_agent": "chat",
  "default_sub_route": "general_chat",
  "rules": [],
  "agents": []
}
```

### 15.2 模拟路由

```http
POST /v1/agent-ops/routing/simulate
```

请求：

```json
{
  "query": "帮我检测这张图片是否合格",
  "attachments": [
    {
      "kind": "image",
      "name": "product.png"
    }
  ],
  "ext": {
    "selected_rag_space": null
  }
}
```

返回：

```json
{
  "matched_rule": "P2 图片 + 检测意图",
  "selected_agent": "inspection_task",
  "selected_sub_route": "inspection_execute",
  "route_source": "rule",
  "reason": "图片 + 检测意图",
  "signals": {
    "has_image": true,
    "has_quality_signal": true
  }
}
```

### 15.3 获取最近路由事件

```http
GET /v1/agent-ops/routing/events?limit=20
```

### 15.4 获取路由统计

```http
GET /v1/agent-ops/routing/metrics
```

---

## 16. 数据库是否需要变更

本版不需要做数据库可配置策略表。

不需要新增：

- `routing_policy_versions`
- `routing_rules`
- `route_rule_metrics`

但建议复用并轻微增强现有：

```text
agent_route_logs
```

如果当前日志已经包含：

- selected_agent
- intent_name
- sub_route
- route_source
- reason
- fallback_agent
- signals_json
- latency_ms

那么第一版可以不改数据库。

如果想让最近事件更好展示，可以补充：

| 字段 | 说明 |
|---|---|
| matched_rule_key | 命中的规则 key，如 `image-inspection` |
| matched_rule_name | 命中的规则名，如“图片检测意图” |
| request_summary | 请求摘要 |
| status | 路由后执行状态 |

这些字段不是必须，第一版也可以从已有字段推导。

---

## 17. 实施优先级

### P0：必须先做

1. 页面改版，减少大段文字。
2. 将曲线图改为横向决策流图。
3. 页面展示真实路由结构：`chat / inspection_task`。
4. 展示当前内置规则表。
5. 提供只读规则详情。
6. 提供模拟器，但不允许修改策略。
7. 展示最近路由事件。

### P1：体验增强

1. 路由树与图联动。
2. 点击规则高亮路径。
3. 点击最近事件高亮真实路径。
4. 统计每条规则最近 24h 命中次数。
5. 展示 fallback 或模型分类器触发情况。
6. 增加异常路由提示。

### P2：后续可选

1. 路由规则配置。
2. 策略版本管理。
3. 灰度发布。
4. 回滚。
5. 动态数据库策略。

这些留到后续版本，不进入本版。

---

## 18. 验收标准

### 页面展示

- 页面不再以长段文字为主。
- 路由图清楚展示：请求 → Agent Manager → 信号 → 规则 → Agent → 子路由。
- 页面真实展示当前项目中的 `chat` 和 `inspection_task`。
- 不再把旧概念作为主路由展示。
- 每条内置规则都能在规则表中看到。

### 路由模拟

- 输入图片 + 检测意图，模拟结果为 `inspection_task / inspection_execute`。
- 输入创建任务意图，模拟结果为 `inspection_task / task_create`。
- 输入 RAG 问答，模拟结果为 `chat / rag_qa`。
- 输入普通聊天，模拟结果为 `chat / general_chat`。
- 模拟器只返回路由结果，不执行真实任务。

### 事件观测

- 最近路由事件能展示真实请求的目标 Agent。
- 能看到路由来源是 rule、manual 还是 model_classifier。
- 点击事件后，图中能高亮对应路径。

### 后端

- 当前硬编码路由能被转换为前端展示结构。
- 模拟接口调用真实路由决策逻辑。
- 路由日志可被页面读取。

### 数据库

- 本版不要求新增策略配置表。
- 如已有 `agent_route_logs` 足够使用，可不改数据库。
- 如果需要更好展示命中规则，可轻量增加 matched_rule 字段。

---

## 19. 最终推荐方案一句话

本版路由策略页面不做配置和发布，只做：

```text
真实展示当前内置路由规则
清晰解释 Agent Manager 如何路由
提供模拟器验证路由结果
展示最近真实路由事件
优化图形和页面布局
```

核心变化是：

```text
从“文字堆叠的策略说明页”
升级为
“清晰、可信、可诊断的路由策略查看中心”
```

后续如果确实需要动态配置，再在第二阶段引入数据库策略版本和规则配置。
