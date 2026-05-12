# 5+1 角色统一设计规范

> 基于 PIAP_ROLE_v1_0_0、PIAP_AGENT_FUNCTION_v1_0_0、PIAP_FRONT_BACKEND_UNIFIED_DETAILED_DESIGN_v1_0_0 三份文档

## 实施策略

**方案 A — 全量替换**。一次性删除所有旧角色名称和 legacy 映射，替换为新角色体系。数据库新建迁移脚本更新现有用户数据。不存在向后兼容。

---

## 1. 角色定义

| 常量名 | 中文名 | 数据库值 |
|--------|--------|----------|
| `ROLE_ADMIN` | 系统管理员 | `admin` |
| `ROLE_APP_DEVELOPER` | 应用开发者 | `app_developer` |
| `ROLE_PLATFORM_OPERATOR` | 平台运维员 | `platform_operator` |
| `ROLE_ALGORITHM_ENGINEER` | 算法工程师 | `algorithm_engineer` |
| `ROLE_USER` | 终端用户-标准 | `user` |
| `ROLE_EXPERT` | 终端用户-专业 | `expert` |

`api_service` 保留为机器身份，不计入用户角色。

### 删除内容

- 删除全部 6 个旧常量：`ROLE_INSPECTOR`、`ROLE_ANALYST`、`ROLE_AGENT_OPERATOR`、`ROLE_API_SERVICE`
- 移除 `LEGACY_ROLE_MAP` 字典及 `normalize_role()` 函数
- 移除 `domain/user.py` 中的旧 Role 枚举
- 删除 migration 0012 中的 legacy 映射逻辑

### 旧→新映射（供数据库迁移参考）

| 旧 role | → 新 role |
|---------|-----------|
| `inspector` | `user` |
| `analyst` | `algorithm_engineer` |
| `agent_operator` | `app_developer` |
| `super_admin`, `org_admin`, `platform_admin`, `auditor` | `admin` |
| `viewer` | `user` |
| `ai_quality` | `algorithm_engineer` |

---

## 2. 工作台分配

| 角色 | app | ops | governance |
|------|:---:|:---:|:----------:|
| admin | ✓ | ✓ | ✓ |
| app_developer | — | ✓ | — |
| platform_operator | — | ✓ | ✓ |
| algorithm_engineer | — | ✓ | ✓ |
| user | ✓ | — | — |
| expert | ✓ | — | — |

**默认工作台**: admin → governance, app_developer → ops, platform_operator → ops, algorithm_engineer → governance, user/expert → app

---

## 3. Capability 能力分配

| Capability | admin | app_dev | plat_op | algo_eng | user | expert |
|------------|:-----:|:-------:|:-------:|:--------:|:----:|:------:|
| private_rag | — | — | — | — | — | ✓ |
| custom_prompt | — | — | — | — | — | ✓ |
| custom_workflow | ✓ | ✓ | — | — | — | ✓ |
| cot_control | ✓ | — | — | ✓ | — | ✓ |
| governance_console | ✓ | — | ✓ | ✓ | — | — |
| model_control | ✓ | — | — | ✓ | — | — |
| advanced_analytics | ✓ | — | ✓ | ✓ | — | — |

**硬约束**: `private_rag` 和 `custom_prompt` 仅 expert 拥有；只有 user 和 expert 能使用 chat 功能。

---

## 4. 资源权限矩阵

| 资源 | admin | app_dev | plat_op | algo_eng | user | expert |
|------|:-----:|:-------:|:-------:|:--------:|:----:|:------:|
| user | ✓ | — | — | — | — | — |
| task | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| result | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| stability | ✓ | ✓ | ✓ | ✓ | — | — |
| alert | ✓ | ✓ | ✓ | ✓ | — | — |
| tool | ✓ | ✓ | ✓ | ✓ | — | — |
| analytics | ✓ | ✓ | ✓ | ✓ | — | — |
| audit | ✓ | — | — | — | — | — |
| model_config | ✓ | — | — | ✓ | — | — |
| inspection_spec | ✓ | ✓ | — | ✓ | — | — |
| billing | ✓ | — | — | — | — | — |
| feedback | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| quality | ✓ | ✓ | ✓ | ✓ | — | — |
| agent_ops | ✓ | ✓ | ✓ | — | — | — |
| chat | — | — | — | — | ✓ | ✓ |

---

## 5. 菜单结构

### 规则

- **工作台分组仅 admin 可见**，其他角色扁平显示菜单项
- 对话（chat）仅 user / expert 可见
- RAG 空间仅 expert 可见
- ✅ = 已实现页面，🚧 = 空白占位页

### 5.1 admin（系统管理员）— 31 项

```
◆ 应用工作台
  ├ Dashboard            ✅  /app/dashboard
  ├ 任务管理              ✅  /app/tasks
  ├ 检测结果              ✅  /app/results
  └ 反馈管理              ✅  /app/feedbacks
◆ 运维工作台
  ├ Agent 管理            ✅  /ops/agents
  ├ Prompt 管理           ✅  /ops/prompts
  ├ RAG 配置              ✅  /ops/rag
  ├ 分析看板              ✅  /ops/analytics
  ├ 发布管理              ✅  /ops/releases
  └ 计费管理              ✅  /ops/billing
◆ 治理工作台
  ├ 用户管理              ✅  /governance/admin/users
  ├ 角色与菜单            🚧  /governance/admin/roles
  ├ 租户/组织             🚧  /governance/admin/orgs
  ├ 模型配置              ✅  /governance/admin/models
  ├ 存储/基础设施          🚧  /governance/admin/infrastructure
  ├ GPU 调度              ✅  /governance/admin/gpu
  ├ 检测标准              ✅  /governance/admin/inspection-specs
  ├ 质量报告              ✅  /governance/quality/report
  ├ 质量追踪              ✅  /governance/quality/tracing
  ├ 记忆治理              🚧  /governance/memory
  ├ 登录日志              🚧  /governance/admin/auth-logs
  ├ 审计日志              ✅  /governance/admin/audit-logs
  └ 高风险审批            🚧  /governance/admin/approvals
◆ 个人设置                ✅  /app/profile
```

### 5.2 app_developer（应用开发者）— 11 项

```
  Agent 管理              ✅  /ops/agents
  Agent 拓扑图            🚧  /ops/agents/topology
  路由策略                🚧  /ops/agents/intent-routes
  Prompt 管理             ✅  /ops/prompts
  DSPy 优化               🚧  /ops/prompts/dspy
  RAG 配置                ✅  /ops/rag
  召回策略                🚧  /ops/rag/policies
  流程节点                🚧  /ops/workflows
  工具注册                🚧  /ops/tools
  发布管理                ✅  /ops/releases
  个人设置                ✅  /app/profile
```

### 5.3 platform_operator（平台运维员）— 15 项

```
  Agent 管理              ✅  /ops/agents
  模板审核                🚧  /ops/templates/review
  发布协同                ✅  /ops/releases
  模型版本                🚧  /ops/models/versions
  调用监控                🚧  /ops/models/monitor
  数据质量                🚧  /ops/data-quality
  标注任务                🚧  /ops/label-tasks
  数据审核                🚧  /ops/data-review
  用户行为分析            🚧  /ops/analytics/behavior
  业务报表                🚧  /ops/analytics/reports
  成本分析                🚧  /ops/analytics/cost
  质量报告                ✅  /governance/quality/report
  质量追踪                ✅  /governance/quality/tracing
  记忆治理                🚧  /governance/memory
  个人设置                ✅  /app/profile
```

### 5.4 algorithm_engineer（算法工程师）— 15 项

```
  数据接入                🚧  /ops/data/import
  数据处理                🚧  /ops/data/processing
  测试集管理              🚧  /ops/data/eval-sets
  训练任务                🚧  /ops/training/jobs
  微调管理                🚧  /ops/training/fine-tune
  离线评测                🚧  /ops/eval/offline
  在线验证                🚧  /ops/eval/online
  实验追踪                🚧  /ops/experiments
  部署记录                🚧  /ops/deployments
  模型配置                ✅  /governance/admin/models
  检测标准                ✅  /governance/admin/inspection-specs
  质量报告                ✅  /governance/quality/report
  质量追踪                ✅  /governance/quality/tracing
  记忆治理                🚧  /governance/memory
  个人设置                ✅  /app/profile
```

### 5.5 user（终端用户-标准）— 7 项

```
  AI 检测对话              ✅  /app/chat
  任务管理                 ✅  /app/tasks
  检测结果                 ✅  /app/results
  证据溯源                 ✅  /app/results/:id/evidence
  异常反馈                 ✅  /app/feedbacks
  报告导出                 🚧  /app/export
  个人设置                 ✅  /app/profile
```

### 5.6 expert（终端用户-专业）— 8 项

```
  AI 检测对话              ✅  /app/chat
  RAG 空间                 ✅  /app/rag-spaces
  任务管理                 ✅  /app/tasks
  检测结果                 ✅  /app/results
  证据溯源                 ✅  /app/results/:id/evidence
  异常反馈                 ✅  /app/feedbacks
  报告导出                 🚧  /app/export
  个人设置                 ✅  /app/profile
```

---

## 6. 前端路由结构

```
/app
  ├ /dashboard          [所有角色]
  ├ /chat               [user, expert]
  ├ /rag-spaces         [expert]
  ├ /tasks              [所有角色]
  ├ /results            [所有角色]
  ├ /results/:id        [所有角色]
  ├ /feedbacks          [所有角色]
  ├ /export             [user, expert] 🚧
  └ /profile            [所有角色]

/ops
  ├ /agents             [admin, app_developer, platform_operator]
  ├ /agents/topology    [app_developer] 🚧
  ├ /agents/intent-routes [app_developer] 🚧
  ├ /prompts            [admin, app_developer]
  ├ /prompts/dspy       [app_developer] 🚧
  ├ /rag                [admin, app_developer]
  ├ /rag/policies       [app_developer] 🚧
  ├ /workflows          [app_developer] 🚧
  ├ /tools              [app_developer] 🚧
  ├ /releases           [admin, app_developer, platform_operator]
  ├ /analytics          [admin, platform_operator]
  ├ /analytics/behavior [platform_operator] 🚧
  ├ /analytics/reports  [platform_operator] 🚧
  ├ /analytics/cost     [platform_operator] 🚧
  ├ /billing            [admin]
  ├ /templates/review   [platform_operator] 🚧
  ├ /models/versions    [platform_operator] 🚧
  ├ /models/monitor     [platform_operator] 🚧
  ├ /data-quality      [platform_operator] 🚧
  ├ /label-tasks       [platform_operator] 🚧
  ├ /data-review       [platform_operator] 🚧
  ├ /data/import        [algorithm_engineer] 🚧
  ├ /data/processing    [algorithm_engineer] 🚧
  ├ /data/eval-sets     [algorithm_engineer] 🚧
  ├ /training/jobs      [algorithm_engineer] 🚧
  ├ /training/fine-tune [algorithm_engineer] 🚧
  ├ /eval/offline       [algorithm_engineer] 🚧
  ├ /eval/online        [algorithm_engineer] 🚧
  ├ /experiments        [algorithm_engineer] 🚧
  └ /deployments        [algorithm_engineer] 🚧

/governance
  ├ /admin/users        [admin]
  ├ /admin/roles        [admin] 🚧
  ├ /admin/orgs         [admin] 🚧
  ├ /admin/models       [admin, algorithm_engineer]
  ├ /admin/infrastructure [admin] 🚧
  ├ /admin/gpu          [admin]
  ├ /admin/inspection-specs [admin, algorithm_engineer]
  ├ /admin/auth-logs    [admin] 🚧
  ├ /admin/audit-logs   [admin]
  ├ /admin/approvals    [admin] 🚧
  ├ /quality/report     [admin, platform_operator, algorithm_engineer]
  ├ /quality/tracing    [admin, platform_operator, algorithm_engineer]
  └ /memory             [admin, platform_operator, algorithm_engineer] 🚧
```

---

## 7. 改动范围

### 后端 (backend/)

| 文件 | 改动 |
|------|------|
| `app/core/permissions.py` | 替换 6 个角色常量，重写 PERMISSIONS 矩阵，删除 LEGACY_ROLE_MAP |
| `app/core/claims.py` | 重写 `derive_workspaces()`、`derive_capabilities()`、`derive_default_workspace()` |
| `app/domain/user.py` | 删除旧 Role 枚举或同步为新值 |
| `app/models/user.py` | 修改 role 列 default 值 |
| `app/schemas/user.py` | 修改 role default |
| `app/services/user_service.py` | 修改 `get_assignable_roles()` |
| `app/services/auth_service.py` | 修改注册默认角色 |
| `app/services/chat_service.py` | 修改 chat 权限检查 |
| `app/services/task_service.py` | 修改 role scope 逻辑 |
| `app/api/v1/deps.py` | 修改 token 解析角色逻辑 |
| `app/api/v1/*.py` | 修改 require_role() 调用中的角色参数 |
| `migrations/versions/` | 新增迁移脚本更新已有用户 role |
| `migrations/data/0021_seed_demo_snapshot.json` | 更新种子数据 role |

### 前端 (frontend/)

| 文件 | 改动 |
|------|------|
| `src/constants/roles.ts` | 替换角色常量，删除 LEGACY_ROLE_MAP 和 normalizeRole() |
| `src/stores/auth.store.ts` | 重写 workspace 推导、defaultRoute 推导、roleLabel 映射 |
| `src/composables/usePermission.ts` | 适配新角色常量 |
| `src/router/index.ts` | 重写路由守卫，适配新角色 |
| `src/router/routes/app.routes.ts` | 更新 route meta roles |
| `src/router/routes/ops.routes.ts` | 更新 route meta roles，新增占位路由 |
| `src/router/routes/governance.routes.ts` | 更新 route meta roles，新增占位路由 |
| `src/layouts/AppLayout.vue` | 重写侧边栏菜单渲染 |
| `src/views/UserListView.vue` | 更新 roleMeta 标签映射 |
| `src/views/DashboardView.vue` | 更新 isAdmin 判断 |
| `src/types/auth.types.ts` | 更新 role 类型（如需） |
| 新增 30+ 占位页面 | `src/views/placeholder/*.vue` |

### 数据库

| 表 | 改动 |
|------|------|
| `users.role` | 新迁移将已有用户映射到新 role 值 |
| `audit.actor_role` | 历史数据不做迁移（只追加） |
| `tool.access_roles` | JSON 列中的旧 role 值需更新 |
| 种子数据 | 更新 demo snapshot 中所有 role 值 |

---

## 8. 验收标准

| # | 标准 |
|---|------|
| 1 | 6 种角色登录后各见各自菜单，无越权菜单出现 |
| 2 | admin 显示三个工作台分组，其他角色扁平菜单 |
| 3 | 仅 user / expert 看到对话入口，仅 expert 看到 RAG 空间 |
| 4 | 🚧 占位页面显示"功能开发中" |
| 5 | 路由守卫阻止越权访问 |
| 6 | 后端 API 对各角色权限正确拒绝/放行 |
| 7 | 数据库 users 表不再包含旧 role 值 |
| 8 | 代码库搜索无 `inspector`、`analyst`、`agent_operator`、`super_admin`、`org_admin`、`platform_admin`、`auditor`、`viewer`、`ai_quality`、`api_service` 等旧常量 |
