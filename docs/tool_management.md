# 工具管理中心实现说明

## 目标

工具管理中心用于统一管理平台内可被 Agent 调用的工具能力，覆盖以下范围：

- 工具总览
- 工具库
- 外部导入
- Agent 绑定
- 执行监控
- 工具详情页中的配置、测试、版本、绑定和执行记录

当前实现已经以数据库为运行时事实源，核心模型统一到：

- `tool_definitions`
- `tool_versions`
- `agent_tool_bindings`

旧表 `tool_registry` 仅保留为迁移兼容和回滚缓冲，不再作为业务主读写模型。

## 菜单结构

左侧导航采用一级入口加二级子菜单的形式：

```text
RAG 分析
工具管理
  - 工具总览
  - 工具库
  - 外部导入
  - Agent 绑定
  - 执行监控
```

说明：

- `工具管理` 与 `RAG 分析` 为并列一级菜单。
- `工具详情` 为隐藏路由，不直接出现在菜单中。
- 工具详情路径为 `/ops/tools/catalog/:id`。

## 前端页面职责

### 1. 工具总览 `/ops/tools`

用于展示整体状态，不承担重编辑职责。

包含：

- 工具总数、启用数、异常数、今日调用数
- 工具分类分布
- 健康状态概览
- 最近执行趋势

### 2. 工具库 `/ops/tools/catalog`

用于浏览、筛选和进入工具详情。

包含：

- 搜索
- 分类筛选
- 状态筛选
- 风险等级筛选
- 来源筛选
- 卡片视图与表格视图

### 3. 外部导入 `/ops/tools/import`

当前支持：

- 内置工具同步
- OpenAPI 规范导入
- MCP Server 工具发现
- 手动创建 HTTP 工具的入口引导

### 4. Agent 绑定 `/ops/tools/bindings`

用于按 Agent 控制工具可见性与可调用范围。

### 5. 执行监控 `/ops/tools/executions`

用于查看工具执行记录、状态、耗时、错误和追踪信息。

### 6. 工具详情 `/ops/tools/catalog/:id`

包含以下信息区：

- 概览
- 配置
- 参数 Schema
- 测试
- Agent 绑定
- 执行记录
- 版本历史
- 审计信息

## 数据模型

### `tool_definitions`

职责：保存工具的稳定身份和运营属性。

关键字段：

- `id`
- `org_id`
- `tool_key`
- `display_name`
- `description`
- `category`
- `tool_type`
- `status`
- `risk_level`
- `is_readonly`
- `source_type`
- `source_ref`
- `manifest_hash`
- `active_version_id`
- `health_status`

唯一约束：

- `uk_org_tool_key`

### `tool_versions`

职责：保存工具的具体可执行版本。

关键字段：

- `id`
- `tool_id`
- `version`
- `endpoint`
- `method`
- `handler_path`
- `parameters_schema`
- `returns_schema`
- `auth_type`
- `secret_ref`
- `timeout_ms`
- `retry_policy`
- `rate_limit_rpm`

唯一约束：

- `uk_tool_version`

### `agent_tool_bindings`

职责：控制 Agent 与工具版本之间的绑定关系。

关键字段：

- `agent_id`
- `tool_id`
- `tool_version_id`
- `binding_status`
- `allowed_intents`
- `approval_required`
- `auto_call_enabled`

唯一约束：

- `uk_agent_tool`

### 兼容表 `tool_registry`

该表仅保留用于：

- 历史数据迁移
- 旧环境回滚缓冲
- 已有 `tool_executions.tool_id` 数据关系平滑过渡

业务代码不应再直接依赖该表。

## 后端实现边界

### 当前主读写链路

以下服务已切换到新模型：

- `backend/app/repositories/tool_repo.py`
- `backend/app/services/tool_service.py`
- `backend/app/services/tool_version_service.py`
- `backend/app/services/tool_sync_service.py`
- `backend/app/services/tool_import_service.py`
- `backend/agent/tools/resolver.py`
- `backend/agent/tools/guard.py`
- `backend/app/services/tool_health_service.py`

### 运行时解析

Agent 运行时通过 `ToolResolver` 读取：

- `tool_definitions`
- `tool_versions`
- `agent_tool_bindings`

只向 Agent 暴露已绑定且可用的工具版本。

### 执行记录

工具测试与运行时调用都会写入：

- `tool_executions`

区分字段：

- `execution_type = test`
- `execution_type = runtime`

## 导入与同步行为

### 内置工具同步

扫描 `backend/agent/tools/builtin/` 中的内置工具定义，写入：

- `tool_definitions`
- `tool_versions`

如果 `manifest_hash` 变化，则创建新版本并切换 `active_version_id`。

### OpenAPI 导入

将 OpenAPI 规范解析为 HTTP 工具定义，并直接落库到新模型。

### MCP 导入

当前为发现与预览入口，后续可继续增强为正式导入流程。

## 数据迁移

迁移脚本：

- `backend/migrations/versions/0044_migrate_tool_registry_to_definitions.py`

作用：

- 将旧 `tool_registry` 数据迁移到 `tool_definitions`
- 为每条旧工具生成一条初始 `tool_versions`
- 将 `tool_definitions.active_version_id` 指向迁移生成的版本
- 复用旧 `tool_registry.id` 作为 `tool_definitions.id`

这样可以避免现有 `tool_executions.tool_id` 失联。

## 部署与升级步骤

### 升级前

1. 备份数据库。
2. 确认应用实例已停止写入迁移中的工具表。
3. 确认当前环境的 Alembic 版本链完整。

### 升级执行

1. 执行 `alembic upgrade head`。
2. 确认 `0044_migrate_tool_registry_to_definitions.py` 已执行。
3. 启动应用。
4. 执行一次内置工具同步。

### 升级后核对

建议至少核对以下内容：

1. `tool_definitions` 行数是否符合预期。
2. 每个定义是否存在一条可用 `tool_versions`。
3. `active_version_id` 是否已正确回填。
4. `agent_tool_bindings` 页面读写是否正常。
5. 工具总览、工具库、详情、测试、执行监控是否可正常访问。
6. 内置工具测试和 OpenAPI 导入是否可正常落库。

## 测试与验证

建议最少执行以下命令：

```bash
pytest -q
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```

说明：

- `backend/tests/conftest.py` 已补充 `backend` 目录到 `sys.path`，从仓库根目录执行 `pytest -q` 不再因 `infra` 模块缺失失败。

## 约束与后续建议

当前保留的兼容面仅剩数据库中的旧表模型定义本身，目的是降低迁移风险。后续如需彻底下线旧表，建议按以下顺序推进：

1. 连续多个版本观察新模型运行稳定性。
2. 确认无任何脚本或外部任务再读取 `tool_registry`。
3. 清理最终兼容迁移和旧表定义。
4. 再执行正式删表迁移。
