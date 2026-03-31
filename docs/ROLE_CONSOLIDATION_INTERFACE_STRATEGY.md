# PIAP 角色合并接口策略

> 基于 PIAP_INT_008 三工作台协作规范，定义角色精简后的接口兼容策略

## 一、背景

将原有 10 个角色精简为 5 个角色：

| 新角色 | 合并来源 |
|--------|----------|
| `admin` | super_admin + org_admin + platform_admin + auditor |
| `inspector` | inspector + viewer |
| `analyst` | analyst + ai_quality |
| `agent_operator` | (保留) |
| `api_service` | (保留) |

## 二、接口兼容策略

### 2.1 后端接口层

#### 2.1.1 权限检查兼容

所有 `require_role()` 调用自动支持旧角色映射：

```python
# permissions.py 中的 LEGACY_ROLE_MAP
LEGACY_ROLE_MAP = {
    "super_admin": "admin",
    "org_admin": "admin",
    "platform_admin": "admin",
    "auditor": "admin",
    "viewer": "inspector",
    "ai_quality": "analyst",
}

def require_role(resource: str, role: str) -> None:
    normalized = LEGACY_ROLE_MAP.get(role, role)  # 自动映射旧角色
    allowed = PERMISSIONS.get(resource, set())
    if normalized not in allowed:
        raise ForbiddenError(f"role {role} cannot access {resource}")
```

#### 2.1.2 JWT Claims 兼容

后端在解析 JWT 时，自动将旧角色映射为新角色：

```python
def normalize_roles(role: str | None, roles: list[str] | None) -> list[str]:
    normalized = [LEGACY_ROLE_MAP.get(r, r) for r in (roles or [])]
    if role:
        primary = LEGACY_ROLE_MAP.get(role, role)
        if primary not in normalized:
            normalized.insert(0, primary)
    return normalized
```

#### 2.1.3 登录响应兼容

登录接口返回新角色，但保持向后兼容：

```json
{
  "access_token": "jwt-token",
  "org_id": "org_01J...",
  "user_id": "usr_01J...",
  "role": "admin",
  "roles": ["admin"],
  "plan_tier": "premium",
  "capabilities": ["private_rag", "custom_workflow"],
  "workspaces": ["app", "governance"],
  "default_workspace": "governance"
}
```

### 2.2 前端接口层

#### 2.2.1 角色常量兼容

前端提供 `normalizeRole()` 函数，确保旧角色自动映射：

```typescript
// constants/roles.ts
export const LEGACY_ROLE_MAP: Record<string, string> = {
  super_admin: ROLE_ADMIN,
  org_admin: ROLE_ADMIN,
  platform_admin: ROLE_ADMIN,
  auditor: ROLE_ADMIN,
  viewer: ROLE_INSPECTOR,
  ai_quality: ROLE_ANALYST,
};

export function normalizeRole(role: string): string {
  return LEGACY_ROLE_MAP[role] || role;
}
```

#### 2.2.2 权限判断兼容

所有权限判断函数都使用 `normalizeRole()` 处理：

```typescript
// composables/usePermission.ts
function hasRole(requiredRole: string | string[]): boolean {
  const normalizedRoles = currentRoles.map(normalizeRole);
  if (normalizedRoles.includes(ROLE_ADMIN)) return true;
  // ...
}
```

#### 2.2.3 工作台推导兼容

根据新角色推导用户可访问的工作台：

```typescript
// stores/auth.store.ts
const normalizedRoles = roles.value.map(normalizeRole);
if (!workspaces.value.length) {
  if (normalizedRoles.includes(ROLE_ADMIN) || normalizedRoles.includes(ROLE_ANALYST)) {
    workspaces.value = [WORKSPACE_GOVERNANCE];
  } else if (normalizedRoles.includes(ROLE_AGENT_OPERATOR)) {
    workspaces.value = [WORKSPACE_OPS];
  } else {
    workspaces.value = [WORKSPACE_APP];
  }
}
```

## 三、三工作台接口契约

### 3.1 A端（应用工作台）→ C端（治理工作台）

| 输入类别 | 字段 | C端用途 | 角色权限 |
|----------|------|---------|----------|
| 用户套餐上下文 | plan_tier / capabilities / rag_space_id | 预算、配额、GPU优先级 | admin, inspector, analyst |
| 反馈提交 | result_id / score / feedback_type / comment / trace_id | 质量闭环、Langfuse Score | inspector, analyst |
| 任务业务上下文 | task_id / workflow_binding / product_line / priority_hint | 预算与质量分析 | inspector, analyst |

### 3.2 B端（运维工作台）→ C端（治理工作台）

| 输入类别 | 字段 | C端用途 | 角色权限 |
|----------|------|---------|----------|
| 实验摘要 | experiment_id / control_version / treatment_version | 发布评审 A/B 依据 | agent_operator, admin |
| 版本资产 | prompt_version / workflow_version / intent_config_id | 发布内容与回滚目标 | agent_operator, admin |
| 召回质量摘要 | retrieval_hit_rate / citation_coverage / faithfulness | 质量门禁判断 | agent_operator, admin |
| 发布申请 | release_id / scope / risk_note / rollback_target | 审批、灰度、回滚 | admin |

### 3.3 C端（治理工作台）→ A/B端

| 输出类别 | 字段 | 消费端动作 | 角色权限 |
|----------|------|-----------|----------|
| 策略快照 | plan_quota / budget_status / gpu_class / allowed_models | 调整可用功能与UI提示 | admin |
| 发布状态 | release_id / status / canary_ratio / rollback_reason | 展示发布进度、切换模型 | admin, agent_operator |
| 质量告警 | quality_alert_id / severity / dimension / target_scope | 提示降级、进入修复流程 | admin, analyst |
| 平台告警 | budget_warn / provider_degraded / gpu_exhausted | 影响可用能力与实验窗口 | admin |

## 四、路由权限映射

### 4.1 应用工作台路由

| 路径 | 新角色权限 | 旧角色兼容 |
|------|-----------|-----------|
| /app/dashboard | 所有已登录用户 | super_admin, org_admin, inspector, viewer, analyst, ai_quality, agent_operator |
| /app/tasks | admin, inspector, analyst, agent_operator | super_admin, org_admin, inspector, viewer, analyst, ai_quality, agent_operator |
| /app/results | admin, inspector, analyst, agent_operator | 同上 |
| /app/stability | admin, inspector, analyst, agent_operator | 同上 |
| /app/alerts | admin, inspector, analyst, agent_operator | 同上 |
| /app/analytics | admin, inspector, analyst, agent_operator | 同上 |
| /app/users | admin | super_admin, org_admin |

### 4.2 运维工作台路由

| 路径 | 新角色权限 | 旧角色兼容 |
|------|-----------|-----------|
| /ops/runtime | admin, agent_operator | super_admin, agent_operator |

### 4.3 治理工作台路由

| 路径 | 新角色权限 | 旧角色兼容 |
|------|-----------|-----------|
| /governance/quality/report | admin, analyst | super_admin, ai_quality |
| /governance/quality/tracing | admin, analyst | super_admin, ai_quality |
| /governance/quality/feedbacks | admin, analyst | super_admin, ai_quality |
| /governance/admin/inspection-specs | admin, analyst | super_admin, platform_admin, ai_quality, org_admin |
| /governance/admin/models | admin | super_admin, platform_admin |
| /governance/admin/billing | admin | super_admin, platform_admin, org_admin |
| /governance/admin/gpu | admin | super_admin, platform_admin |

## 五、SSE 事件规范

| 事件 | 主要消费端 | 含义 | 角色范围 |
|------|-----------|------|----------|
| task.progress | A端 | 任务执行中 | inspector, analyst, agent_operator |
| task.complete | A端 | 结果已完成 | inspector, analyst, agent_operator |
| release.status_changed | B/C端 | 发布单状态切换 | admin, agent_operator |
| budget.warn | A/B/C端 | 预算接近阈值 | admin |
| quality.alert | B/C端 | 质量门禁异常 | admin, analyst |
| model.degraded | A/B/C端 | 供应商或模型降级 | admin, agent_operator |
| trace.ready | C端 | Trace可查看 | admin, analyst |

## 六、数据库迁移策略

### 6.1 迁移脚本

```sql
-- 0012_consolidate_roles.py
UPDATE users SET role = 'admin' WHERE role IN ('super_admin', 'org_admin', 'platform_admin', 'auditor');
UPDATE users SET role = 'inspector' WHERE role = 'viewer';
UPDATE users SET role = 'analyst' WHERE role = 'ai_quality';
```

### 6.2 回滚策略

```sql
-- downgrade: 无法精确还原，统一回退到 inspector
UPDATE users SET role = 'inspector' WHERE role IN ('admin', 'analyst');
```

## 七、验收清单

| 验收域 | 通过标准 | 角色 |
|--------|----------|------|
| 身份与菜单 | 同一账号登录后仅看到有权限的workspace与菜单 | 所有角色 |
| A→C 反馈闭环 | A端点踩/类型标注后，C端质量页可看到 | inspector, analyst |
| B→C 发布链路 | B端提交Draft发布后，C端能审批、灰度、回滚 | admin, agent_operator |
| 同库协作 | 所有数据来自同一套逻辑数据库 | 所有角色 |
| 统一主键链 | request_id / task_id / trace_id / ledger_id 能串联 | 所有角色 |
| 治理控制生效 | 预算预警、模型降级能影响可用能力 | admin |

## 八、协作开发规则

### 8.1 分支命名

- `feature/a-*` - 应用工作台功能
- `feature/b-*` - 运维工作台功能
- `feature/c-*` - 治理工作台功能
- `feature/shared-*` - 共享功能（角色、权限、认证）

### 8.2 评审 RACI

| 事项 | 主责 | 提交者 | 评审要求 |
|------|------|--------|----------|
| 共享 Auth / Workspace | A、B、C 共担 | 任一人 | 至少两人 |
| 角色与权限变更 | shared | 提出方 | 其余两人至少一人 |
| Migration 变更 | 提出方 | 提出方 | 其余两人 + DBA/架构师 |

## 九、结论

1. **向后兼容**：所有接口通过 `LEGACY_ROLE_MAP` 自动支持旧角色，无需前端改动
2. **渐进迁移**：数据库迁移后，旧角色自动映射为新角色
3. **统一控制面**：遵循 PIAP_INT_008 规范，保持"一套平台、三个工作台、同一控制面"
