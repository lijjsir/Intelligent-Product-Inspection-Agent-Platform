# Agent Operator And Workspace Claims Contract

## 目标

本文件冻结 `agent_operator + workspace claims` 的最小实施契约。

适用范围：

- 鉴权与 JWT
- 登录返回结构
- 前端工作台切换
- 三端协作中的角色边界

若后续实现与本文件冲突，以本文件为准，除非另有正式 ADR。

## 统一结论

1. 新增人工角色 `agent_operator`
2. `A.1/A.2` 不拆成新的 RBAC 角色，统一视图层语义为 `end_user`
3. JWT 不再只返回单一 `role`，而是返回工作台所需的完整 claims
4. 前端必须按 `workspace` 决定默认首页和菜单显隐
5. 后端鉴权仍以服务端 RBAC/ABAC 为准，前端 claims 只负责体验层路由与菜单

## 角色模型

### 现有控制台角色

- `super_admin`
- `platform_admin`
- `org_admin`
- `inspector`
- `viewer`
- `analyst`
- `auditor`
- `ai_quality`
- `agent_operator`

### 服务主体

- `api_service`

### 角色语义

- `agent_operator`
  - 负责租户内 Agent 配置、Prompt/Workflow 版本、Intent、实验和召回分析
  - 不可直接修改平台治理控制面
  - 不可直接操作 `model_configs`、预算、GPU、账单控制面

### A 端实施语义

- 产品语义中的 `end_user` 不作为新的后端 RBAC 强制角色引入
- 在当前实现阶段，A 端可继续复用 `inspector` 作为最小兼容角色
- 若后续需要完全对齐 `008`，可再增加 `end_user` 作为显示层/接口层角色映射

## Workspace 模型

### 枚举

- `app`
- `ops`
- `governance`

### 语义

- `app`
  - 面向任务、结果、私有 RAG、业务看板、反馈
- `ops`
  - 面向 Agent 配置、Prompt、Workflow、Intent、实验、召回分析
- `governance`
  - 面向平台治理和 AI 质量
  - 物理上包含：
    - `/admin/*`
    - `/quality/*`

## Plan Tier 枚举

- `basic`
- `premium`
- `expert`

## Capability 枚举

当前先冻结以下能力项：

- `private_rag`
- `gpu_priority`
- `custom_workflow`
- `business_dashboard`
- `high_quota`

## JWT Claims Contract

### 必需字段

```json
{
  "sub": "usr_01J...",
  "org_id": "org_01J...",
  "roles": ["agent_operator"],
  "plan_tier": "premium",
  "capabilities": ["private_rag", "custom_workflow"],
  "workspaces": ["app", "ops"],
  "default_workspace": "ops"
}
```

### 字段定义

- `sub`
  - 用户主键
- `org_id`
  - 租户主键
- `roles`
  - 角色数组
  - 即使当前只有一个角色，也统一使用数组
- `plan_tier`
  - 套餐层级
- `capabilities`
  - 能力项数组
- `workspaces`
  - 当前登录用户可访问的工作台数组
- `default_workspace`
  - 登录后的默认工作台

### 向后兼容

当前系统已有单字段 `role`。兼容策略：

- 后端过渡期同时返回：
  - `role`
  - `roles`
- 前端优先读 `roles`
- 当全部前端切换完成后，再考虑降级 `role` 为兼容字段

## 登录响应 Contract

建议统一响应结构：

```json
{
  "access_token": "jwt-token",
  "org_id": "org_01J...",
  "user_id": "usr_01J...",
  "role": "agent_operator",
  "roles": ["agent_operator"],
  "plan_tier": "premium",
  "capabilities": ["private_rag", "custom_workflow"],
  "workspaces": ["app", "ops"],
  "default_workspace": "ops"
}
```

## 前端 Auth Store Contract

前端 `auth.store` 应新增以下状态：

- `roles: string[]`
- `planTier: string`
- `capabilities: string[]`
- `workspaces: string[]`
- `defaultWorkspace: string`

前端应新增以下方法：

- `hasRole(role: string | string[])`
- `hasCapability(capability: string | string[])`
- `hasWorkspace(workspace: string | string[])`
- `resolveDefaultWorkspace()`

## 工作台路由策略

### 目标结构

- `/app/*`
- `/ops/*`
- `/governance/*`

### 当前项目过渡要求

当前项目可以暂时不重构全部路由，但必须做到：

1. 登录后能根据 `default_workspace` 重定向
2. 菜单按 workspace 分组
3. `governance` 逻辑上统一承载：
   - `/admin/*`
   - `/quality/*`

## 后端实现清单

以下文件后续实现时应优先修改：

- `backend/app/core/permissions.py`
- `backend/app/schemas/user.py`
- `backend/app/models/user.py`
- `backend/app/api/v1/auth.py`
- `backend/app/services/auth_service.py`

建议新增实体：

- `user_entitlements`

建议字段：

- `id`
- `org_id`
- `user_id`
- `plan_tier`
- `capabilities_json`
- `default_workspace`
- `created_at`
- `updated_at`

## 前端实现清单

- `frontend/src/stores/auth.store.ts`
- `frontend/src/types/auth.types.ts`
- `frontend/src/router/index.ts`
- `frontend/src/layouts/*`
- `frontend/src/composables/usePermission.ts`

## 冻结规则

以下字段在三人并行开发阶段视为冻结：

- `roles`
- `plan_tier`
- `capabilities`
- `workspaces`
- `default_workspace`
- `agent_operator`
- `app / ops / governance`

任何改动必须先改 contract 文档，再改前后端实现。
