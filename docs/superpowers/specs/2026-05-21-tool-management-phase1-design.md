# 工具管理第一阶段真实化改造设计
> 依据文档：`docs/tool_management.md`
> 实施范围：第一阶段 + 修复现有明显断点
> 验收口径：开发环境真实可用

---

## 1. 目标

将 `/ops/tools` 从“页面结构基本齐全，但部分能力依赖 preview/mock、部分接口为占位实现”的状态，升级为开发环境下真实可用的第一阶段产品。

本次改造只聚焦文档中的第一阶段目标：

1. 工具总览页真实可用
2. 工具库页真实可用
3. 工具详情页真实可用
4. 工具测试 Tab 真实可用
5. 执行记录 Tab / 执行监控页真实可用
6. 修复当前已暴露的错误、假实现、筛选失效、前端展示异常

本次不做第二、第三阶段的完整建设，但会把未完成能力处理成“诚实降级”，避免继续误导开发和测试。

---

## 2. 范围边界

### 2.1 本轮必须完成

#### 前端

1. `/ops/tools` 工具总览页接入真实后端统计
2. `/ops/tools/catalog` 工具库页接入真实搜索、筛选、分页、状态切换、创建工具
3. `/ops/tools/catalog/:id` 工具详情页接入真实详情、配置编辑、Schema 展示、测试、执行记录
4. `/ops/tools/executions` 执行监控页接入真实日志与真实统计
5. 去除第一阶段页面中的 preview/mock 依赖，让默认开发环境走真实后端
6. 修复工具管理相关页面中的中文编码污染、错误文案、交互误导和 lint 问题

#### 后端

1. `GET /v1/tools/overview`
2. `GET /v1/tools`
3. `GET /v1/tools/{id}`
4. `POST /v1/tools`
5. `PUT /v1/tools/{id}`
6. `PATCH /v1/tools/{id}/status`
7. `POST /v1/tools/{id}/test`
8. `GET /v1/tools/{id}/executions`
9. `GET /v1/tools/executions`
10. `GET /v1/tools/executions/overview`
11. `POST /v1/tools/sync/builtin`

#### 数据与运行

1. 继续复用 `tool_registry + tool_executions`
2. 将内置工具 manifest 同步到数据库
3. 将真实测试调用和真实执行日志写入 `tool_executions`
4. 修复筛选逻辑和统计逻辑，使页面展示与真实数据一致

### 2.2 本轮明确不做

以下能力不在本轮实现范围内，但必须从“伪已实现”调整为“明确未开放”：

1. `tool_definitions / tool_versions / agent_tool_bindings` 三表重构
2. 真实版本创建、发布、回滚
3. Agent 绑定矩阵真实持久化与运行时生效
4. OpenAPI / MCP 导入真链路
5. SSE / WebSocket 事件流
6. ToolGuard 审批流、高风险人工确认、完整密钥治理

---

## 3. 当前问题归纳

### 3.1 用户可见问题

1. 版本、绑定、导入页面存在 preview/mock 结果，容易误导为已完成能力
2. 工具库“异常”筛选与后端真实语义不一致
3. 执行监控页的执行类型筛选在真实后端不生效
4. 详情页中的版本历史、Agent 绑定、审计日志并非真实实体数据
5. 页面与 mock 数据中存在中文编码污染和展示异常

### 3.2 后端逻辑问题

1. 绑定接口是占位实现
2. 版本发布/回滚接口是占位实现
3. `test_tool` 是 dry-run，不是真执行
4. 执行记录查询未真正支持 `execution_type`、`agent_id`
5. `count_executions` 采用内存计数，效率较差
6. `list_active` 未覆盖全局内置工具可见性
7. ToolResolver 仍是“所有 active 工具对所有 Agent 可见”

### 3.3 工程问题

1. 第一阶段相关页面默认仍可被 previewMocks 接管
2. 工具管理相关前端文件存在 lint 问题
3. 文档和实际实现存在明显错位

---

## 4. 设计原则

1. **先做真实可用，再做架构升级**
   第一阶段优先保证主流程可用，避免同时推进大表拆分和多子系统改造。

2. **诚实降级，不保留假成功**
   本轮未实现能力可以保留信息架构，但不能继续提供伪造成功交互。

3. **页面默认走真实后端**
   第一阶段页面的默认开发行为必须基于真实接口，而不是 preview/mock。

4. **状态与健康分离**
   工具生命周期状态与运行健康状态分开表达，避免前后端对“异常”的定义冲突。

5. **执行日志作为第一阶段事实源**
   总览统计、详情摘要、监控图表优先从 `tool_executions` 推导。

---

## 5. 总体方案

### 5.1 数据层策略

本轮不做三表重构，继续以现有两张表为核心：

1. `tool_registry` 作为工具定义与当前有效配置的载体
2. `tool_executions` 作为测试执行与运行执行日志的事实源

在现有模型基础上补齐第一阶段所需的真实字段语义：

1. `tool_registry`
   - 保留 `category / tool_type / status / risk_level / source_type / health_status / manifest_hash`
   - 继续使用 `version` 表示当前有效版本号，但只作为字符串展示，不扩展为独立版本实体

2. `tool_executions`
   - 使用 `execution_type` 区分 `runtime / test`
   - 使用 `agent_id / trace_id / input_redacted / output_redacted` 支撑执行监控展示

### 5.2 后端服务策略

`ToolService` 作为第一阶段唯一真实业务入口，负责：

1. 工具列表查询与筛选
2. 工具详情组装
3. 工具基础信息编辑
4. 工具状态切换
5. 工具测试执行
6. 执行记录查询
7. 总览统计与执行监控统计

`ToolRepository` 负责真实数据查询，避免服务层大量内存后处理。

`ToolSyncService` 负责内置工具同步，将 `backend/agent/tools/builtin/` 的 manifest 落到数据库。

### 5.3 前端页面策略

保留文档第一阶段所需主页面：

1. 工具总览页
2. 工具库页
3. 工具详情页
4. 执行监控页

对超出第一阶段的页面和 Tab 做降级：

1. `ToolImportView`
   - 调整为“能力预告 + 内置工具同步入口”
   - 不再提供 OpenAPI / MCP 假导入流程

2. `ToolBindingView`
   - 调整为“第二阶段开放说明”或隐藏菜单入口
   - 不再提供 mock 绑定矩阵编辑

3. `ToolDetailView`
   - 第一阶段保留真实 Tab：概览、配置、参数 Schema、测试、执行记录
   - 第二阶段 Tab：Agent 绑定、版本历史、审计日志
     - 要么隐藏
     - 要么明确显示“第二阶段开放”，不得继续走 mock 接口

推荐方案：隐藏第二阶段 Tab，仅保留第一阶段真实功能。

---

## 6. 后端详细设计

### 6.1 API 收口

#### 保留并做实

1. `GET /v1/tools/overview`
2. `GET /v1/tools`
3. `GET /v1/tools/{id}`
4. `POST /v1/tools`
5. `PUT /v1/tools/{id}`
6. `PATCH /v1/tools/{id}/status`
7. `POST /v1/tools/{id}/test`
8. `GET /v1/tools/{id}/executions`
9. `GET /v1/tools/executions`
10. `GET /v1/tools/executions/overview`
11. `POST /v1/tools/sync/builtin`

#### 诚实降级

以下接口本轮不再伪装为已完成能力：

1. `GET /v1/tools/bindings`
2. `POST /v1/tools/bindings`
3. `DELETE /v1/tools/bindings/{id}`
4. `POST /v1/tools/{id}/versions`
5. `POST /v1/tools/{id}/versions/{version_id}/publish`
6. `POST /v1/tools/{id}/versions/{version_id}/rollback`
7. `GET /v1/tools/events/stream`

处理策略：

1. 若前端本轮已移除调用，则接口可保留但明确返回未开放说明
2. 不再返回会被误判为“真实成功”的 mock 风格 payload

### 6.2 ToolRepository

补强仓储查询能力：

1. `list_all`
   - 支持按 `keyword / category / status / risk_level / source_type / has_binding` 查询
   - 第一阶段 `has_binding` 默认无法基于真实绑定表判断，可移除该筛选或明确返回空能力

2. `list_executions`
   - 支持 `tool_id / status / execution_type / agent_id / page / size`

3. `count_executions`
   - 使用数据库 count，而不是全量拉取后 `len(...)`

4. `list_recent_executions`
   - 用于总览趋势和工具详情摘要

5. `list_active`
   - 需支持 `org_id == 当前组织` 或 `org_id is null`
   - 确保全局内置工具可见

### 6.3 ToolService

#### 工具列表

`list_tools` 需要返回：

1. 基础定义字段
2. 今日调用量
3. 成功率
4. 平均延迟
5. 健康状态

其中：

1. `status` 表示工具生命周期，如 `active / disabled / draft / deprecated`
2. `health_status` 表示运行健康，如 `healthy / degraded / unhealthy / unknown`

“异常工具”应基于 `health_status` 而不是伪造 `status=error`。

#### 工具详情

`get_tool_detail` 第一阶段仅返回真实内容：

1. 基础定义信息
2. 配置信息
3. `parameters_schema / returns_schema`
4. 最近执行记录
5. 测试结果相关信息
6. 当前版本字符串

不再返回伪造的：

1. 版本列表
2. 绑定列表
3. 审计日志

#### 工具编辑

第一阶段只允许更新低风险定义字段：

1. `display_name`
2. `description`
3. `category`
4. `risk_level`
5. `is_readonly`

不支持在第一阶段通过页面修改：

1. `version`
2. 真实版本历史
3. 绑定关系

#### 工具测试

`test_tool` 必须由 dry-run 升级为真实执行：

1. `native`
   - 根据 `handler_path` 动态导入并调用

2. `http / openapi`
   - 真实发起 HTTP 请求
   - 第一阶段以最基础请求为主，不做复杂鉴权治理

3. `rag`
   - 优先复用现有内置 handler
   - 若当前代码库没有统一 RAG handler 入口，则在第一阶段通过 builtin 包装函数适配

测试结果写入 `tool_executions`：

1. `execution_type = test`
2. `status = success / failed / timeout`
3. `trace_id` 可追踪
4. `input_payload / output_payload` 与必要的脱敏字段一并写入

#### 执行监控

`list_executions` 与 `get_execution_overview` 必须共享一套真实语义：

1. 状态筛选真实生效
2. 执行类型筛选真实生效
3. Agent 维度筛选真实生效
4. 趋势图基于最近 24 小时执行日志

### 6.4 ToolSyncService

`scan_and_sync` 保留，并收口为第一阶段真实入口。

同步行为：

1. 扫描 builtin modules 中的 `TOOL_MANIFESTS`
2. 根据 `tool_key` 判断新增或更新
3. 写入 `manifest_hash`
4. 更新 `display_name / description / parameters_schema / returns_schema / risk_level / category / tool_type`

不做：

1. 新版本草稿创建
2. 外部变化审阅流

### 6.5 ToolResolver

本轮不做 Agent 绑定真实落地，因此 `ToolResolver` 不纳入第一阶段验收主链路。

仅做两项收口：

1. 注释与能力说明改为第一阶段真实状态，避免继续宣称已按绑定过滤
2. 保持现有“active 工具可见”的 MVP 逻辑，但不再与页面绑定页产生假联动预期

---

## 7. 前端详细设计

### 7.1 API 层

`frontend/src/api/tools.api.ts` 调整原则：

1. 第一阶段页面默认走真实后端
2. 去除 `previewMocks` 对第一阶段能力的默认接管
3. 未实现能力不再伪造成功结果

处理方式：

1. `getOverview / listTools / getTool / createTool / updateTool / updateToolStatus / testTool / listExecutions / getExecutionOverview / syncBuiltin`
   - 全部走真实接口

2. `createVersion / publishVersion / rollbackVersion / getBindingMatrix / listBindings / createBinding / updateBinding / deleteBinding`
   - 本轮前端不再默认调用
   - 若保留函数，则仅作为第二阶段保留接口，不接入当前页面

### 7.2 工具总览页

保留现有信息结构：

1. Hero 区
2. 统计卡片
3. 调用趋势 / 错误趋势 / 健康分布
4. 关注事项

修正点：

1. 图表全部来自真实 `overview`
2. 文案统一修复
3. 不再出现乱码或错误标签

### 7.3 工具库页

保留：

1. 搜索框
2. 分类/状态/风险/来源筛选
3. 卡片/表格视图
4. 创建工具
5. 停用工具
6. 轻量测试入口

调整：

1. “异常”筛选从 `status=error` 改为基于 `health_status`
2. 若本轮无法真实支持“已绑定/未绑定 Agent”筛选，则先移除该筛选项
3. 详情按钮跳转到真实详情页

### 7.4 工具详情页

第一阶段最终保留 Tab：

1. 概览
2. 配置
3. 参数 Schema
4. 测试
5. 执行记录

第一阶段移除或隐藏：

1. Agent 绑定
2. 版本历史
3. 审计日志

这样可以保证用户进入详情页时看到的全部内容都是真能力。

### 7.5 执行监控页

保留：

1. 顶部统计
2. 调用趋势 / 错误趋势 / 延迟趋势
3. 日志表格
4. 状态 / 执行类型筛选

必须修复：

1. 执行类型筛选真正生效
2. 状态文案正确
3. Agent 名称为空时给出清晰展示

### 7.6 导入页

本轮改造成“第一阶段诚实降级页”：

1. 显示第二、三阶段计划说明
2. 保留“内置工具同步”按钮
3. 不再展示 OpenAPI / MCP 的 mock Stepper 成功流程

### 7.7 绑定页

本轮改造成“第二阶段预留页”：

1. 显示当前未开放原因
2. 说明后续会引入真实 `agent_tool_bindings`
3. 不再展示 mock 矩阵和假保存行为

如菜单层需要更克制，也可直接隐藏该入口。

---

## 8. 文件级改造范围

### 后端

1. `backend/app/api/v1/tools.py`
2. `backend/app/models/tool.py`
3. `backend/app/repositories/tool_repo.py`
4. `backend/app/schemas/tool.py`
5. `backend/app/services/tool_service.py`
6. `backend/app/services/tool_sync_service.py`
7. `backend/agent/tools/resolver.py`
8. `backend/tests/test_tools_api.py`
9. 可能新增工具服务或执行相关测试文件

### 前端

1. `frontend/src/api/tools.api.ts`
2. `frontend/src/api/tools.mock.ts`
3. `frontend/src/stores/tools.store.ts`
4. `frontend/src/types/tools.types.ts`
5. `frontend/src/router/routes/ops.routes.ts`
6. `frontend/src/composables/useMenu.ts`
7. `frontend/src/views/ops/tools/ToolOverviewView.vue`
8. `frontend/src/views/ops/tools/ToolCatalogView.vue`
9. `frontend/src/views/ops/tools/ToolDetailView.vue`
10. `frontend/src/views/ops/tools/ToolExecutionView.vue`
11. `frontend/src/views/ops/tools/ToolImportView.vue`
12. `frontend/src/views/ops/tools/ToolBindingView.vue`

### 文档

1. `docs/tool_management.md`
   - 调整为与第一阶段真实状态一致
   - 未完成能力明确标为第二阶段/第三阶段

---

## 9. 实施顺序

### 阶段 A：后端做实

1. 修正 schema、repository、service 的第一阶段能力
2. 补齐测试执行真实链路
3. 修复执行监控查询与统计
4. 做实 builtin sync
5. 补齐后端测试

### 阶段 B：前端去假留真

1. API 层移除第一阶段 preview 接管
2. 调整 store 和类型定义
3. 工具库、详情、监控页对齐真实后端语义
4. 移除/隐藏第二阶段假交互
5. 修复中文展示与 lint 问题

### 阶段 C：文档和验收

1. 更新 `docs/tool_management.md`
2. 跑后端测试
3. 跑前端 typecheck
4. 跑前端 build
5. 跑前端 lint，并明确区分本轮修复范围与全仓历史债

---

## 10. 验收标准

### 10.1 后端

以下接口在开发环境真实可用：

1. `GET /v1/tools/overview`
2. `GET /v1/tools`
3. `GET /v1/tools/{id}`
4. `POST /v1/tools`
5. `PUT /v1/tools/{id}`
6. `PATCH /v1/tools/{id}/status`
7. `POST /v1/tools/{id}/test`
8. `GET /v1/tools/{id}/executions`
9. `GET /v1/tools/executions`
10. `GET /v1/tools/executions/overview`
11. `POST /v1/tools/sync/builtin`

### 10.2 前端

以下页面默认走真实后端，且主流程可用：

1. `/ops/tools`
2. `/ops/tools/catalog`
3. `/ops/tools/catalog/:id`
4. `/ops/tools/executions`

### 10.3 测试与工程

1. 工具测试不再是 dry-run 假成功
2. 执行记录筛选真实生效
3. 第一阶段相关后端测试通过
4. 前端 `typecheck` 通过
5. 前端 `build` 通过
6. 工具管理相关 lint 错误修复完成

### 10.4 体验

1. 不再出现“看起来可点，但实际是假能力”的页面
2. 第一阶段功能真实可演示、可测试、可追踪
3. 第二、三阶段能力边界清楚，不误导用户

---

## 11. 风险与取舍

1. 继续复用 `tool_registry` 会保留结构债，但能显著降低本轮风险
2. 不做三表重构意味着版本与绑定只能在下一阶段彻底落地
3. 若部分 builtin/native/rag 工具的真实 handler 不满足统一调用要求，本轮应优先保证“真实失败”而不是继续伪造成功
4. 文档需同步调整，否则会继续出现“文档已完成、实现未完成”的认知偏差

---

## 12. 结论

本轮采用“**MVP 真闭环**”策略：

1. 不做大规模表结构升级
2. 先把第一阶段工具管理的用户主流程做成真实能力
3. 同时去掉当前的 mock 假象和明显错误
4. 将第二、三阶段能力明确降级，不再伪装为可用

这样可以在风险可控的前提下，把工具管理从“半成品演示态”推进到“开发环境真实可用态”，为后续版本化、绑定、导入和实时事件能力打下稳定基础。
