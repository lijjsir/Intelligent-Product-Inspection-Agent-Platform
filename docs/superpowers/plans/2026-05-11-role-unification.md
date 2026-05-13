# 6 角色统一实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all 6 old roles + legacy mappings with 6 new roles (admin, app_developer, platform_operator, algorithm_engineer, user, expert), rebuild permission matrix, update all frontend menus/route guards, and migrate database.

**Architecture:** Backend-first approach — define new role constants and permissions → update services/API → run DB migration → update frontend constants/stores → rebuild route guards → rewrite sidebar → add placeholder pages.

**Tech Stack:** Python/FastAPI/Pydantic/SQLAlchemy/Alembic (backend), Vue 3/Pinia/Vue Router/Element Plus (frontend), MySQL (database).

---

### Task 1: Rewrite backend role constants and PERMISSIONS matrix

**Files:**
- Modify: `backend/app/core/permissions.py` (entire file)

- [ ] **Step 1: Replace entire permissions.py**

```python
from __future__ import annotations

from typing import Dict, Set

from app.core.exceptions import ForbiddenError, ValidationError


ROLE_ADMIN = "admin"
ROLE_APP_DEVELOPER = "app_developer"
ROLE_PLATFORM_OPERATOR = "platform_operator"
ROLE_ALGORITHM_ENGINEER = "algorithm_engineer"
ROLE_USER = "user"
ROLE_EXPERT = "expert"

ALL_ROLES = {
    ROLE_ADMIN,
    ROLE_APP_DEVELOPER,
    ROLE_PLATFORM_OPERATOR,
    ROLE_ALGORITHM_ENGINEER,
    ROLE_USER,
    ROLE_EXPERT,
}

PERMISSIONS: Dict[str, Set[str]] = {
    "user": {ROLE_ADMIN},
    "task": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER, ROLE_USER, ROLE_EXPERT},
    "result": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER, ROLE_USER, ROLE_EXPERT},
    "stability": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER},
    "alert": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER},
    "tool": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER},
    "analytics": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER},
    "audit": {ROLE_ADMIN},
    "model_config": {ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER},
    "inspection_spec": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_ALGORITHM_ENGINEER},
    "billing": {ROLE_ADMIN},
    "feedback": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER, ROLE_USER, ROLE_EXPERT},
    "quality": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER},
    "agent_ops": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR},
    "chat": {ROLE_USER, ROLE_EXPERT},
}


def require_role(resource: str, role: str) -> None:
    allowed = PERMISSIONS.get(resource, set())
    if role not in allowed:
        raise ForbiddenError(f"role {role} cannot access {resource}")


def ensure_valid_role(role: str) -> None:
    if role not in ALL_ROLES:
        raise ValidationError(f"invalid role: {role}")
```

Key changes:
- Remove all 6 old constants (`ROLE_INSPECTOR`, `ROLE_ANALYST`, `ROLE_AGENT_OPERATOR`, `ROLE_API_SERVICE` plus `LEGACY_ROLE_MAP`, `normalize_role`)
- Add 6 new constants
- Rewrite PERMISSIONS per spec
- `require_role()` no longer normalizes — checks directly
- `ensure_valid_role()` checks against ALL_ROLES directly

- [ ] **Step 2: Run existing tests to see what breaks**

Run: `cd backend && python -m pytest tests/ -x --timeout=30 2>&1 | tail -40`
Expected: Many failures due to missing old role constants

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/permissions.py
git commit -m "feat: replace role constants and PERMISSIONS matrix with 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Rewrite claims.py (workspace, capability, default workspace)

**Files:**
- Modify: `backend/app/core/claims.py` (entire file)

- [ ] **Step 1: Replace claims.py**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.permissions import (
    ROLE_ADMIN,
    ROLE_APP_DEVELOPER,
    ROLE_ALGORITHM_ENGINEER,
    ROLE_PLATFORM_OPERATOR,
    ROLE_USER,
    ROLE_EXPERT,
)


WORKSPACE_APP = "app"
WORKSPACE_OPS = "ops"
WORKSPACE_GOVERNANCE = "governance"

PLAN_BASIC = "basic"
PLAN_PREMIUM = "premium"
PLAN_ENTERPRISE = "enterprise"

CAPABILITY_PRIVATE_RAG = "private_rag"
CAPABILITY_CUSTOM_PROMPT = "custom_prompt"
CAPABILITY_CUSTOM_WORKFLOW = "custom_workflow"
CAPABILITY_COT_CONTROL = "cot_control"
CAPABILITY_GOVERNANCE = "governance_console"
CAPABILITY_ADVANCED_ANALYTICS = "advanced_analytics"
CAPABILITY_MODEL_CONTROL = "model_control"


@dataclass(frozen=True)
class AuthClaims:
    role: str
    roles: list[str]
    plan_tier: str
    capabilities: list[str]
    workspaces: list[str]
    default_workspace: str

    def as_token_extra(self, org_id: str) -> dict[str, Any]:
        return {
            "org_id": org_id,
            "role": self.role,
            "roles": self.roles,
            "plan_tier": self.plan_tier,
            "capabilities": self.capabilities,
            "workspaces": self.workspaces,
            "default_workspace": self.default_workspace,
        }


def normalize_roles(role: str | None = None, roles: list[str] | None = None) -> list[str]:
    normalized = [str(item) for item in (roles or []) if item]
    if role and role not in normalized:
        normalized.insert(0, role)
    return normalized


def derive_plan_tier(plan: str | None) -> str:
    value = str(plan or "").lower()
    if value in {"premium", "pro"}:
        return PLAN_PREMIUM
    if value in {"enterprise", "expert"}:
        return PLAN_ENTERPRISE
    return PLAN_BASIC


def derive_capabilities(plan_tier: str, roles: list[str]) -> list[str]:
    capabilities: set[str] = set()
    if ROLE_EXPERT in roles:
        capabilities.add(CAPABILITY_PRIVATE_RAG)
        capabilities.add(CAPABILITY_CUSTOM_PROMPT)
    if any(r in {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_EXPERT} for r in roles):
        capabilities.add(CAPABILITY_CUSTOM_WORKFLOW)
    if any(r in {ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER, ROLE_EXPERT} for r in roles):
        capabilities.add(CAPABILITY_COT_CONTROL)
    if any(r in {ROLE_ADMIN, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER} for r in roles):
        capabilities.add(CAPABILITY_GOVERNANCE)
    if any(r in {ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER} for r in roles):
        capabilities.add(CAPABILITY_MODEL_CONTROL)
    if any(r in {ROLE_ADMIN, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER} for r in roles):
        capabilities.add(CAPABILITY_ADVANCED_ANALYTICS)
    if plan_tier in {PLAN_PREMIUM, PLAN_ENTERPRISE}:
        capabilities.add(CAPABILITY_CUSTOM_WORKFLOW)
        capabilities.add(CAPABILITY_ADVANCED_ANALYTICS)
    if plan_tier == PLAN_ENTERPRISE:
        capabilities.add(CAPABILITY_MODEL_CONTROL)
    return sorted(capabilities)


def derive_workspaces(roles: list[str]) -> list[str]:
    workspaces: list[str] = []
    if any(r in {ROLE_ADMIN, ROLE_USER, ROLE_EXPERT} for r in roles):
        workspaces.append(WORKSPACE_APP)
    if any(r in {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER} for r in roles):
        workspaces.append(WORKSPACE_OPS)
    if any(r in {ROLE_ADMIN, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER} for r in roles):
        workspaces.append(WORKSPACE_GOVERNANCE)
    if not workspaces:
        workspaces.append(WORKSPACE_APP)
    return workspaces


def derive_default_workspace(roles: list[str], workspaces: list[str]) -> str:
    if ROLE_ADMIN in roles:
        return WORKSPACE_GOVERNANCE
    if ROLE_ALGORITHM_ENGINEER in roles:
        return WORKSPACE_GOVERNANCE
    if ROLE_APP_DEVELOPER in roles:
        return WORKSPACE_OPS
    if ROLE_PLATFORM_OPERATOR in roles:
        return WORKSPACE_OPS
    return workspaces[0] if workspaces else WORKSPACE_APP


def build_auth_claims(primary_role: str, organization_plan: str | None = None) -> AuthClaims:
    roles = normalize_roles(role=primary_role)
    plan_tier = derive_plan_tier(organization_plan)
    workspaces = derive_workspaces(roles)
    return AuthClaims(
        role=primary_role,
        roles=roles,
        plan_tier=plan_tier,
        capabilities=derive_capabilities(plan_tier, roles),
        workspaces=workspaces,
        default_workspace=derive_default_workspace(roles, workspaces),
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/claims.py
git commit -m "feat: rewrite workspace/capability derivation for 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Update domain/user.py Role enum

**Files:**
- Modify: `backend/app/domain/user.py`

- [ ] **Step 1: Replace domain/user.py**

```python
from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    admin = "admin"
    app_developer = "app_developer"
    platform_operator = "platform_operator"
    algorithm_engineer = "algorithm_engineer"
    user = "user"
    expert = "expert"
    api_service = "api_service"


@dataclass(frozen=True)
class User:
    id: str
    org_id: str
    username: str
    email: str
    role: Role
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/domain/user.py
git commit -m "feat: update domain Role enum to 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Update models and schemas default role values

**Files:**
- Modify: `backend/app/models/user.py:15`
- Modify: `backend/app/schemas/user.py:23`

- [ ] **Step 1: Change User model default role**

In `backend/app/models/user.py` line 15, change:
```python
role: Mapped[str] = mapped_column(String(32), default="inspector")
```
to:
```python
role: Mapped[str] = mapped_column(String(32), default="user")
```

- [ ] **Step 2: Change UserCreate schema default role**

In `backend/app/schemas/user.py` line 23, change:
```python
role: str = "inspector"
```
to:
```python
role: str = "user"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/user.py backend/app/schemas/user.py
git commit -m "feat: update default role to 'user' in model and schema

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Update backend services for new roles

**Files:**
- Modify: `backend/app/services/user_service.py:126-136`
- Modify: `backend/app/services/inspection_spec_service.py:7,12-13`

- [ ] **Step 1: Update user_service.py imports and get_assignable_roles**

Replace the import block (lines 6-13) in `backend/app/services/user_service.py`:
```python
from app.core.permissions import (
    ROLE_ADMIN,
    ROLE_APP_DEVELOPER,
    ROLE_ALGORITHM_ENGINEER,
    ROLE_PLATFORM_OPERATOR,
    ROLE_USER,
    ROLE_EXPERT,
    ensure_valid_role,
)
```

Replace `get_assignable_roles` (lines 126-136):
```python
@staticmethod
def get_assignable_roles(actor_role: str) -> list[str]:
    if actor_role == ROLE_ADMIN:
        return [
            ROLE_ADMIN,
            ROLE_APP_DEVELOPER,
            ROLE_PLATFORM_OPERATOR,
            ROLE_ALGORITHM_ENGINEER,
            ROLE_USER,
            ROLE_EXPERT,
        ]
    return []
```

Replace `_ensure_assignable_role` (lines 138-143):
```python
@staticmethod
def _ensure_assignable_role(actor_role: str, target_role: str) -> None:
    if actor_role == ROLE_ADMIN:
        return
    raise ForbiddenError(f"role {actor_role} cannot assign {target_role}")
```

- [ ] **Step 2: Update inspection_spec_service.py**

Replace line 7:
```python
from app.core.permissions import ROLE_ALGORITHM_ENGINEER
```

Replace lines 12-13:
```python
GLOBAL_SPEC_LEGACY_ROLES: set[str] = set()
GLOBAL_SPEC_NORMALIZED_ROLES = {ROLE_ALGORITHM_ENGINEER}
```

- [ ] **Step 3: Update chat_service.py role scope**

Read `backend/app/services/chat_service.py` first, then update any `ROLE_USER` check to use new role names. The chat scope: `ROLE_USER` and `ROLE_EXPERT` get owner-only scope; others (that can't chat) shouldn't reach this code.

In `backend/app/services/chat_service.py`, find `ROLE_USER` references and ensure `ROLE_EXPERT` has same treatment:
```python
# If there's a check like:
# if actor_role == ROLE_USER: return user_id
# Change to:
# if actor_role in {ROLE_USER, ROLE_EXPERT}: return user_id
```

- [ ] **Step 4: Update task_service.py role scope**

In `backend/app/services/task_service.py`, find any role-based scope logic and update:
```python
# Old: _owner_user_id returns self for ROLE_USER
# New: return self for ROLE_USER, ROLE_EXPERT
# Old: _task_scope_org_id returns None for ROLE_ADMIN
# New: same, but add ROLE_PLATFORM_OPERATOR if needed
```

- [ ] **Step 5: Update billing_service.py admin check**

In `backend/app/services/billing_service.py`, find `actor_role == "admin"` and ensure it uses `ROLE_ADMIN` constant.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/user_service.py backend/app/services/inspection_spec_service.py backend/app/services/chat_service.py backend/app/services/task_service.py backend/app/services/billing_service.py
git commit -m "feat: update all services to use 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Update deps.py and API endpoint require_role calls

**Files:**
- Modify: `backend/app/api/v1/deps.py:27-52`
- Modify: All API files using `require_role()` with old role strings

- [ ] **Step 1: Update deps.py**

Replace `backend/app/api/v1/deps.py` `get_current_user` function (lines 27-52):
```python
def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    if not authorization.startswith("Bearer "):
        raise ForbiddenError("missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = safe_decode_token(token)
    role = payload.get("role", "")
    roles = normalize_roles(role=role, roles=payload.get("roles"))
    workspaces = payload.get("workspaces")
    if not isinstance(workspaces, list) or not workspaces:
        workspaces = derive_workspaces(roles)
    plan_tier = str(payload.get("plan_tier") or derive_plan_tier(None))
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list):
        capabilities = derive_capabilities(plan_tier, roles)
    default_ws = payload.get("default_workspace")
    if not default_ws or not isinstance(default_ws, str):
        default_ws = derive_default_workspace(roles, [str(w) for w in workspaces])
    return CurrentUser(
        user_id=payload.get("sub", ""),
        org_id=payload.get("org_id", ""),
        role=role,
        roles=roles,
        plan_tier=plan_tier,
        capabilities=[str(item) for item in capabilities],
        workspaces=[str(item) for item in workspaces],
        default_workspace=str(default_ws),
    )
```

- [ ] **Step 2: Update all require_role() calls in API files**

Find and update all `require_role("resource", current.role)` calls that reference old role strings in `backend/app/api/v1/*.py`:

```bash
cd backend && grep -rn "require_role" app/api/v1/ --include="*.py"
```

For each file, update role references. Key changes:
- `"agent_operator"` → use `ROLE_APP_DEVELOPER` or `ROLE_PLATFORM_OPERATOR` based on context
- Role strings in `require_role("user", ...)` → keep resource name, the second arg is `current.role`

The `require_role()` calls don't hardcode role names (they pass `current.role`), so they should work after Task 1's PERMISSIONS update. Verify no hardcoded old role strings remain.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/deps.py backend/app/api/v1/
git commit -m "feat: update deps.py and API endpoints for 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Create database migration script

**Files:**
- Create: `backend/migrations/versions/0022_unify_roles_to_6.py`

- [ ] **Step 1: Create migration file**

```python
"""unify roles to 6 new roles

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-11

Mapping:
  super_admin, org_admin, platform_admin, auditor → admin
  inspector, viewer → user
  analyst, ai_quality → algorithm_engineer
  agent_operator → app_developer
  api_service → api_service (keep as machine identity)
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

ROLE_MAP = {
    "super_admin": "admin",
    "org_admin": "admin",
    "platform_admin": "admin",
    "auditor": "admin",
    "inspector": "user",
    "viewer": "user",
    "analyst": "algorithm_engineer",
    "ai_quality": "algorithm_engineer",
    "agent_operator": "app_developer",
}


def upgrade():
    for old, new in ROLE_MAP.items():
        op.execute(
            f"UPDATE users SET role = '{new}' WHERE role = '{old}'"
        )
    # Update tool access_roles JSON
    for old, new in ROLE_MAP.items():
        op.execute(
            f"UPDATE tools SET access_roles = JSON_REPLACE("
            f"  access_roles, "
            f"  JSON_UNQUOTE(JSON_SEARCH(access_roles, 'one', '{old}')), "
            f"  '{new}'"
            f") WHERE JSON_CONTAINS(access_roles, JSON_QUOTE('{old}'))"
        )


def downgrade():
    # Cannot reliably reverse, raise informative error
    raise NotImplementedError(
        "Cannot downgrade role unification. Restore from backup."
    )
```

- [ ] **Step 2: Run migration**

```bash
cd backend && python -m alembic upgrade head
```
Expected: Migration runs successfully, existing user roles updated.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/versions/0022_unify_roles_to_6.py
git commit -m "feat: add migration to unify all roles into 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: Update seed data

**Files:**
- Modify: `backend/migrations/data/0021_seed_demo_snapshot.json`

- [ ] **Step 1: Update role values in seed data**

Replace all old role values in the JSON seed data:
```bash
cd backend
python -c "
import json
with open('migrations/data/0021_seed_demo_snapshot.json') as f:
    data = json.load(f)

role_map = {
    'super_admin': 'admin', 'org_admin': 'admin',
    'platform_admin': 'admin', 'auditor': 'admin',
    'inspector': 'user', 'viewer': 'user',
    'analyst': 'algorithm_engineer', 'ai_quality': 'algorithm_engineer',
    'agent_operator': 'app_developer',
}

text = json.dumps(data)
for old, new in role_map.items():
    text = text.replace(f'\\\"role\\\": \\\"{old}\\\"', f'\\\"role\\\": \\\"{new}\\\"')
with open('migrations/data/0021_seed_demo_snapshot.json', 'w') as f:
    f.write(text)
print('done')
"
```

- [ ] **Step 2: Commit**

```bash
git add backend/migrations/data/0021_seed_demo_snapshot.json
git commit -m "feat: update seed data roles to 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: Rewrite frontend roles.ts constants

**Files:**
- Modify: `frontend/src/constants/roles.ts` (entire file)

- [ ] **Step 1: Replace roles.ts**

```typescript
export const ROLE_ADMIN = "admin";
export const ROLE_APP_DEVELOPER = "app_developer";
export const ROLE_PLATFORM_OPERATOR = "platform_operator";
export const ROLE_ALGORITHM_ENGINEER = "algorithm_engineer";
export const ROLE_USER = "user";
export const ROLE_EXPERT = "expert";

export const ALL_ROLES = [
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_PLATFORM_OPERATOR,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_USER,
  ROLE_EXPERT,
] as const;

export const WORKSPACE_APP = "app";
export const WORKSPACE_OPS = "ops";
export const WORKSPACE_GOVERNANCE = "governance";

export const CAPABILITY_PRIVATE_RAG = "private_rag";
export const CAPABILITY_CUSTOM_PROMPT = "custom_prompt";
export const CAPABILITY_CUSTOM_WORKFLOW = "custom_workflow";
export const CAPABILITY_COT_CONTROL = "cot_control";
export const CAPABILITY_GOVERNANCE = "governance_console";
export const CAPABILITY_ADVANCED_ANALYTICS = "advanced_analytics";
export const CAPABILITY_MODEL_CONTROL = "model_control";
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/constants/roles.ts
git commit -m "feat: replace frontend role constants with 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 10: Rewrite auth.store.ts and usePermission.ts

**Files:**
- Modify: `frontend/src/stores/auth.store.ts`
- Modify: `frontend/src/composables/usePermission.ts`

- [ ] **Step 1: Replace auth.store.ts**

Full replacement of `frontend/src/stores/auth.store.ts`:
```typescript
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { authApi } from "@/api/auth.api";
import { useUserStore } from "@/stores/user.store";
import type { LoginPayload, RegisterPayload, AuthSession } from "@/types/auth.types";
import {
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_PLATFORM_OPERATOR,
  ROLE_USER,
  ROLE_EXPERT,
  WORKSPACE_APP,
  WORKSPACE_GOVERNANCE,
  WORKSPACE_OPS,
} from "@/constants/roles";
import {
  CAPABILITIES_KEY,
  DEFAULT_WORKSPACE_KEY,
  ORG_ID_KEY,
  PLAN_TIER_KEY,
  ROLE_KEY,
  ROLES_KEY,
  TOKEN_KEY,
  USER_ID_KEY,
  USERNAME_KEY,
  WORKSPACES_KEY,
  clearStoredAuthSession,
  readStoredArray,
  readStoredValue,
  setStoredArray,
  setStoredValue,
} from "@/utils/auth-session";

export const useAuthStore = defineStore("auth", () => {
  const token = ref(readStoredValue(TOKEN_KEY));
  const orgId = ref(readStoredValue(ORG_ID_KEY));
  const role = ref(readStoredValue(ROLE_KEY));
  const userId = ref(readStoredValue(USER_ID_KEY));
  const username = ref(readStoredValue(USERNAME_KEY));
  const roles = ref<string[]>(readStoredArray(ROLES_KEY));
  const planTier = ref(readStoredValue(PLAN_TIER_KEY) || "basic");
  const capabilities = ref<string[]>(readStoredArray(CAPABILITIES_KEY));
  const workspaces = ref<string[]>(readStoredArray(WORKSPACES_KEY));
  const defaultWorkspace = ref(readStoredValue(DEFAULT_WORKSPACE_KEY) || WORKSPACE_APP);

  if (!roles.value.length && role.value) {
    roles.value = [role.value];
  }

  function deriveWorkspacesFromRoles(roleList: string[]): string[] {
    const ws: string[] = [];
    if (roleList.some(r => [ROLE_ADMIN, ROLE_USER, ROLE_EXPERT].includes(r))) {
      ws.push(WORKSPACE_APP);
    }
    if (roleList.some(r => [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER].includes(r))) {
      ws.push(WORKSPACE_OPS);
    }
    if (roleList.some(r => [ROLE_ADMIN, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER].includes(r))) {
      ws.push(WORKSPACE_GOVERNANCE);
    }
    return ws.length ? ws : [WORKSPACE_APP];
  }

  function deriveDefaultWorkspaceFromRoles(roleList: string[], wsList: string[]): string {
    if (roleList.includes(ROLE_ADMIN)) return WORKSPACE_GOVERNANCE;
    if (roleList.includes(ROLE_ALGORITHM_ENGINEER)) return WORKSPACE_GOVERNANCE;
    if (roleList.includes(ROLE_APP_DEVELOPER)) return WORKSPACE_OPS;
    if (roleList.includes(ROLE_PLATFORM_OPERATOR)) return WORKSPACE_OPS;
    return wsList[0] || WORKSPACE_APP;
  }

  if (!workspaces.value.length) {
    workspaces.value = deriveWorkspacesFromRoles(roles.value);
  }

  const isAuthed = computed(() => Boolean(token.value));
  const primaryRole = computed(() => role.value || roles.value[0] || "");

  function normalizeRoles(session: AuthSession): string[] {
    const normalized = Array.from(new Set([session.role, ...(session.roles || [])].filter(Boolean)));
    return normalized.length ? normalized : [session.role];
  }

  function setSession(session: AuthSession) {
    const userStore = useUserStore();
    token.value = session.access_token;
    orgId.value = session.org_id;
    role.value = session.role;
    userId.value = session.user_id;
    username.value = session.username;
    roles.value = normalizeRoles(session);
    planTier.value = session.plan_tier || "basic";
    capabilities.value = [...(session.capabilities || [])];
    workspaces.value = [...(session.workspaces || [WORKSPACE_APP])];
    if (!workspaces.value.length) {
      workspaces.value = deriveWorkspacesFromRoles(roles.value);
    }
    defaultWorkspace.value = session.default_workspace || deriveDefaultWorkspaceFromRoles(roles.value, workspaces.value);

    setStoredValue(TOKEN_KEY, token.value);
    setStoredValue(ORG_ID_KEY, orgId.value);
    setStoredValue(ROLE_KEY, role.value);
    setStoredValue(USER_ID_KEY, userId.value);
    setStoredValue(USERNAME_KEY, username.value);
    setStoredArray(ROLES_KEY, roles.value);
    setStoredValue(PLAN_TIER_KEY, planTier.value);
    setStoredArray(CAPABILITIES_KEY, capabilities.value);
    setStoredArray(WORKSPACES_KEY, workspaces.value);
    setStoredValue(DEFAULT_WORKSPACE_KEY, defaultWorkspace.value);
    userStore.current = {
      id: session.user_id,
      org_id: session.org_id,
      username: session.username,
      email: userStore.current?.email || "",
      role: session.role,
      is_active: true,
      created_at: userStore.current?.created_at,
      updated_at: userStore.current?.updated_at,
    };
  }

  async function syncCurrentUserProfile() {
    const userStore = useUserStore();
    try {
      await userStore.fetchCurrentUser();
    } catch (error) {
      console.warn("Failed to refresh current user profile after auth session setup", error);
    }
  }

  async function login(payload: LoginPayload) {
    const { data } = await authApi.login(payload);
    setSession(data.data);
    await syncCurrentUserProfile();
    return data.data;
  }

  async function register(payload: RegisterPayload) {
    const { data } = await authApi.register(payload);
    setSession(data.data);
    await syncCurrentUserProfile();
    return data.data;
  }

  function logout() {
    const userStore = useUserStore();
    token.value = "";
    orgId.value = "";
    role.value = "";
    userId.value = "";
    username.value = "";
    roles.value = [];
    planTier.value = "basic";
    capabilities.value = [];
    workspaces.value = [];
    defaultWorkspace.value = WORKSPACE_APP;
    clearStoredAuthSession();
    userStore.$reset();
  }

  function hasWorkspace(workspace: string) {
    return workspaces.value.includes(workspace);
  }

  function hasCapability(capability: string) {
    return capabilities.value.includes(capability);
  }

  function resolveDefaultRoute() {
    const pr = primaryRole.value;
    if (pr === ROLE_USER || pr === ROLE_EXPERT) {
      return "/app/chat";
    }
    if (pr === ROLE_APP_DEVELOPER) return "/ops/agents";
    if (pr === ROLE_PLATFORM_OPERATOR) return "/ops/agents";
    if (pr === ROLE_ALGORITHM_ENGINEER) return "/governance/quality/report";
    return "/app/dashboard";
  }

  return {
    token, orgId, role, roles, planTier, capabilities, workspaces,
    defaultWorkspace, userId, username, isAuthed, primaryRole,
    login, register, logout, hasWorkspace, hasCapability, resolveDefaultRoute,
  };
});
```

- [ ] **Step 2: Replace usePermission.ts**

```typescript
import { useAuthStore } from "@/stores/auth.store";
import { ROLE_ADMIN } from "@/constants/roles";

export function usePermission() {
  const auth = useAuthStore();

  function hasRole(requiredRole: string | string[]): boolean {
    if (!auth.isAuthed) return false;
    const currentRoles = auth.roles.length ? auth.roles : [auth.role];
    if (currentRoles.includes(ROLE_ADMIN)) return true;
    if (Array.isArray(requiredRole)) {
      return requiredRole.some((role) => currentRoles.includes(role));
    }
    return currentRoles.includes(requiredRole);
  }

  function hasWorkspace(workspace: string | string[]): boolean {
    if (!auth.isAuthed) return false;
    if (Array.isArray(workspace)) {
      return workspace.some((item) => auth.workspaces.includes(item));
    }
    return auth.workspaces.includes(workspace);
  }

  function hasCapability(capability: string | string[]): boolean {
    if (!auth.isAuthed) return false;
    if (Array.isArray(capability)) {
      return capability.some((item) => auth.capabilities.includes(item));
    }
    return auth.capabilities.includes(capability);
  }

  return { hasRole, hasWorkspace, hasCapability };
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/auth.store.ts frontend/src/composables/usePermission.ts
git commit -m "feat: rewrite auth store and permission composable for 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 11: Rewrite frontend router guard

**Files:**
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: Replace router/index.ts**

```typescript
import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";
import { appRoutes } from "@/router/routes/app.routes";
import { opsRoutes } from "@/router/routes/ops.routes";
import { governanceRoutes } from "@/router/routes/governance.routes";
import { ROLE_ADMIN, ROLE_USER, ROLE_EXPERT } from "@/constants/roles";

const routes = [
  {
    path: "/login",
    component: () => import("@/layouts/AuthLayout.vue"),
    children: [
      {
        path: "",
        name: "login",
        component: () => import("@/views/LoginView.vue"),
      },
    ],
  },
  {
    path: "/register",
    component: () => import("@/layouts/AuthLayout.vue"),
    children: [
      {
        path: "",
        name: "register",
        component: () => import("@/views/RegisterView.vue"),
      },
    ],
  },
  {
    path: "/app",
    component: () => import("@/layouts/AppLayout.vue"),
    children: appRoutes,
    meta: { requiresAuth: true },
  },
  {
    path: "/ops",
    component: () => import("@/layouts/AppLayout.vue"),
    children: opsRoutes,
    meta: { requiresAuth: true },
  },
  {
    path: "/governance",
    component: () => import("@/layouts/AppLayout.vue"),
    children: governanceRoutes,
    meta: { requiresAuth: true },
  },
  {
    path: "/users",
    component: () => import("@/layouts/AppLayout.vue"),
    meta: { requiresAuth: true, roles: [ROLE_ADMIN] },
    children: [
      {
        path: "",
        name: "users",
        component: () => import("@/views/UserListView.vue"),
        meta: { title: "用户管理", roles: [ROLE_ADMIN] },
      },
    ],
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/app/dashboard",
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const auth = useAuthStore();

  if (to.meta.requiresAuth && !auth.isAuthed) {
    return { path: "/login" };
  }

  const pr = auth.primaryRole;

  // user/expert can only access app routes for chat, tasks, results, feedbacks, profile
  const endUserAllowedPrefixes = [
    "/app/chat", "/app/rag-spaces", "/app/tasks",
    "/app/results", "/app/feedbacks", "/app/profile", "/app/export",
  ];
  if (auth.isAuthed && (pr === ROLE_USER || pr === ROLE_EXPERT)) {
    const allowed = endUserAllowedPrefixes.some((prefix) => to.path.startsWith(prefix));
    if (!allowed) return { path: "/app/chat" };
  }

  const routeRoles = to.meta.roles as string[] | undefined;
  if (routeRoles) {
    const currentRoles = auth.roles.length ? auth.roles : [auth.role];
    const hasMatch = routeRoles.some((r) => currentRoles.includes(r));
    if (!hasMatch && !currentRoles.includes(ROLE_ADMIN)) {
      return { path: auth.resolveDefaultRoute() };
    }
  }

  if ((to.path === "/login" || to.path === "/register") && auth.isAuthed) {
    return { path: auth.resolveDefaultRoute() };
  }
  return true;
});

export default router;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router/index.ts
git commit -m "feat: rewrite router guard for 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 12: Update app.routes.ts with new role metas

**Files:**
- Modify: `frontend/src/router/routes/app.routes.ts`

- [ ] **Step 1: Replace app.routes.ts**

```typescript
import { ROLE_USER, ROLE_EXPERT } from "@/constants/roles";

export const appRoutes = [
  { path: "dashboard", name: "app-dashboard", component: () => import("@/views/DashboardView.vue") },
  { path: "tasks", name: "app-tasks", component: () => import("@/views/TaskListView.vue"), meta: { title: "任务管理" } },
  { path: "tasks/:id", name: "app-task-detail", component: () => import("@/views/TaskDetailView.vue") },
  { path: "results", name: "app-results", component: () => import("@/views/ResultListView.vue") },
  { path: "results/:id", name: "app-result-detail", component: () => import("@/views/ResultDetailView.vue") },
  { path: "stability", name: "app-stability-overview", component: () => import("@/views/StabilityOverviewView.vue") },
  { path: "stability/:id", name: "app-stability-detail", component: () => import("@/views/StabilityDetailView.vue") },
  { path: "alerts", name: "app-alerts", redirect: "/app/stability?tab=alerts" },
  {
    path: "feedbacks",
    name: "app-feedbacks",
    component: () => import("@/views/quality/FeedbackListView.vue"),
    meta: { title: "反馈流水" },
  },
  { path: "profile", name: "app-profile", component: () => import("@/views/ProfileView.vue") },
  {
    path: "chat",
    name: "app-chat",
    component: () => import("@/views/ChatView.vue"),
    meta: { roles: [ROLE_USER, ROLE_EXPERT] },
  },
  {
    path: "rag-spaces",
    name: "app-rag-spaces",
    component: () => import("@/views/RagSpaceView.vue"),
    meta: { roles: [ROLE_EXPERT] },
  },
  {
    path: "export",
    name: "app-export",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "报告导出", roles: [ROLE_USER, ROLE_EXPERT] },
  },
];
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router/routes/app.routes.ts
git commit -m "feat: update app routes with new role metas and expert RAG access

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 13: Rewrite ops.routes.ts with all role menus

**Files:**
- Modify: `frontend/src/router/routes/ops.routes.ts`

- [ ] **Step 1: Replace ops.routes.ts**

```typescript
import { ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER } from "@/constants/roles";

export const opsRoutes = [
  // -- Shared (admin, app_developer, platform_operator) --
  {
    path: "agents",
    name: "ops-agents",
    component: () => import("@/views/ops/AgentManageView.vue"),
    meta: { title: "Agent 管理", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR] },
  },
  // -- app_developer only --
  {
    path: "agents/topology",
    name: "ops-agents-topology",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "Agent 拓扑图", roles: [ROLE_APP_DEVELOPER] },
  },
  {
    path: "agents/intent-routes",
    name: "ops-agents-intent-routes",
    component: () => import("@/views/ops/IntentRouteView.vue"),
    meta: { title: "路由策略", roles: [ROLE_APP_DEVELOPER] },
  },
  {
    path: "prompts",
    name: "ops-prompts",
    component: () => import("@/views/ops/PromptManageView.vue"),
    meta: { title: "Prompt 管理", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER] },
  },
  {
    path: "prompts/dspy",
    name: "ops-prompts-dspy",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "DSPy 优化", roles: [ROLE_APP_DEVELOPER] },
  },
  {
    path: "rag",
    name: "ops-rag",
    component: () => import("@/views/ops/RagAnalysisView.vue"),
    meta: { title: "RAG 配置", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER] },
  },
  {
    path: "rag/policies",
    name: "ops-rag-policies",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "召回策略", roles: [ROLE_APP_DEVELOPER] },
  },
  {
    path: "workflows",
    name: "ops-workflows",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "流程节点", roles: [ROLE_APP_DEVELOPER] },
  },
  {
    path: "tools",
    name: "ops-tools",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "工具注册", roles: [ROLE_APP_DEVELOPER] },
  },
  // -- Shared (admin, app_developer, platform_operator) --
  {
    path: "releases",
    name: "ops-releases",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "发布管理", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR] },
  },
  // -- admin, platform_operator analytics --
  {
    path: "analytics",
    name: "ops-analytics",
    component: () => import("@/views/AnalyticsView.vue"),
    meta: { title: "分析看板", roles: [ROLE_ADMIN, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "analytics/behavior",
    name: "ops-analytics-behavior",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "用户行为分析", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "analytics/reports",
    name: "ops-analytics-reports",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "业务报表", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "analytics/cost",
    name: "ops-analytics-cost",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "成本分析", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  // -- admin only --
  {
    path: "billing",
    name: "ops-billing",
    component: () => import("@/views/admin/TokenBillingView.vue"),
    meta: { title: "计费管理", roles: [ROLE_ADMIN] },
  },
  {
    path: "runtime",
    name: "ops-runtime",
    component: () => import("@/views/OpsRuntimeView.vue"),
    meta: { title: "Agent 运行态", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR] },
  },
  // -- platform_operator only --
  {
    path: "templates/review",
    name: "ops-templates-review",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "模板审核", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "models/versions",
    name: "ops-models-versions",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "模型版本", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "models/monitor",
    name: "ops-models-monitor",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "调用监控", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "data-quality",
    name: "ops-data-quality",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "数据质量", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "label-tasks",
    name: "ops-label-tasks",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "标注任务", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "data-review",
    name: "ops-data-review",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "数据审核", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  // -- algorithm_engineer only --
  {
    path: "data/import",
    name: "ops-data-import",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "数据接入", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "data/processing",
    name: "ops-data-processing",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "数据处理", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "data/eval-sets",
    name: "ops-data-eval-sets",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "测试集管理", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "training/jobs",
    name: "ops-training-jobs",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "训练任务", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "training/fine-tune",
    name: "ops-training-fine-tune",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "微调管理", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "eval/offline",
    name: "ops-eval-offline",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "离线评测", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "eval/online",
    name: "ops-eval-online",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "在线验证", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "experiments",
    name: "ops-experiments",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "实验追踪", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "deployments",
    name: "ops-deployments",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "部署记录", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
];
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router/routes/ops.routes.ts
git commit -m "feat: rewrite ops routes with full role-based menus and placeholders

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 14: Rewrite governance.routes.ts

**Files:**
- Modify: `frontend/src/router/routes/governance.routes.ts`

- [ ] **Step 1: Replace governance.routes.ts**

```typescript
import { ROLE_ADMIN, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER } from "@/constants/roles";

export const governanceRoutes = [
  // -- admin only --
  {
    path: "admin/users",
    name: "governance-admin-users",
    redirect: "/users",
  },
  {
    path: "admin/roles",
    name: "governance-admin-roles",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "角色与菜单", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/orgs",
    name: "governance-admin-orgs",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "租户/组织", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/infrastructure",
    name: "governance-admin-infrastructure",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "存储/基础设施", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/gpu",
    name: "governance-admin-gpu",
    component: () => import("@/views/admin/GpuMonitorView.vue"),
    meta: { title: "GPU 调度", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/auth-logs",
    name: "governance-admin-auth-logs",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "登录日志", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/audit-logs",
    name: "governance-admin-audit-logs",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "审计日志", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/approvals",
    name: "governance-admin-approvals",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "高风险审批", roles: [ROLE_ADMIN] },
  },
  // -- admin + algorithm_engineer --
  {
    path: "admin/models",
    name: "governance-admin-models",
    component: () => import("@/views/admin/ModelConfigView.vue"),
    meta: { title: "模型配置", roles: [ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "admin/inspection-specs",
    name: "governance-admin-inspection-specs",
    component: () => import("@/views/admin/InspectionSpecView.vue"),
    meta: { title: "检测标准", roles: [ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER] },
  },
  // -- admin + platform_operator + algorithm_engineer --
  {
    path: "quality/report",
    name: "governance-quality-report",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "质量报告", roles: [ROLE_ADMIN, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "quality/tracing",
    name: "governance-quality-tracing",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "质量追踪", roles: [ROLE_ADMIN, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "memory",
    name: "governance-memory",
    component: () => import("@/views/placeholder/PlaceholderView.vue"),
    meta: { title: "记忆治理", roles: [ROLE_ADMIN, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER] },
  },
  // -- retain existing data-management routes for compatibility, gate with ROLE_ADMIN --
  {
    path: "data-management",
    name: "governance-data-management",
    component: () => import("@/views/ops/DataManagementView.vue"),
    meta: { title: "治理工作台", roles: [ROLE_ADMIN] },
  },
  {
    path: "data-management/agents",
    name: "governance-agents",
    component: () => import("@/views/ops/AgentManageView.vue"),
    meta: { title: "Agent 管理", roles: [ROLE_ADMIN] },
  },
  {
    path: "data-management/prompts",
    name: "governance-prompts",
    component: () => import("@/views/ops/PromptManageView.vue"),
    meta: { title: "DSPy 优化工作台", roles: [ROLE_ADMIN] },
  },
  {
    path: "data-management/intent-routes",
    name: "governance-intent-routes",
    component: () => import("@/views/ops/IntentRouteView.vue"),
    meta: { title: "意图路由配置", roles: [ROLE_ADMIN] },
  },
  {
    path: "data-management/inspection-specs",
    name: "governance-inspection-specs",
    component: () => import("@/views/admin/InspectionSpecView.vue"),
    meta: { title: "检测标准", roles: [ROLE_ADMIN] },
  },
];
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router/routes/governance.routes.ts
git commit -m "feat: rewrite governance routes with full role-based menus and placeholders

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 15: Rewrite AppLayout.vue sidebar

**Files:**
- Modify: `frontend/src/layouts/AppLayout.vue`

- [ ] **Step 1: Create menu config composable**

Create `frontend/src/composables/useMenu.ts`:
```typescript
import { computed } from "vue";
import { useAuthStore } from "@/stores/auth.store";
import {
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_PLATFORM_OPERATOR,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_USER,
  ROLE_EXPERT,
  CAPABILITY_PRIVATE_RAG,
} from "@/constants/roles";

interface MenuItem {
  label: string;
  path: string;
  icon?: string;
}

interface MenuSection {
  label: string;
  workspace?: string;
  items: MenuItem[];
  show: () => boolean;
}

export function useMenu() {
  const auth = useAuthStore();

  const isAdmin = computed(() => auth.roles.includes(ROLE_ADMIN));
  const isAppDev = computed(() => auth.roles.includes(ROLE_APP_DEVELOPER));
  const isPlatOp = computed(() => auth.roles.includes(ROLE_PLATFORM_OPERATOR));
  const isAlgoEng = computed(() => auth.roles.includes(ROLE_ALGORITHM_ENGINEER));
  const isUser = computed(() => auth.roles.includes(ROLE_USER));
  const isExpert = computed(() => auth.roles.includes(ROLE_EXPERT));
  const hasPrivateRag = computed(() => auth.capabilities.includes(CAPABILITY_PRIVATE_RAG));

  const sections = computed<MenuSection[]>(() => {
    const result: MenuSection[] = [];

    // Chat section (user, expert only)
    if (isUser.value || isExpert.value) {
      const items: MenuItem[] = [
        { label: "AI 检测对话", path: "/app/chat", icon: "ChatDotRound" },
      ];
      if (hasPrivateRag.value) {
        items.push({ label: "RAG 空间", path: "/app/rag-spaces", icon: "CollectionTag" });
      }
      result.push({ label: "对话", items, show: () => true });
    }

    // App workspace (admin only, as a group)
    if (isAdmin.value) {
      result.push({
        label: "应用工作台",
        workspace: "app",
        items: [
          { label: "Dashboard", path: "/app/dashboard", icon: "DataLine" },
          { label: "任务管理", path: "/app/tasks", icon: "List" },
          { label: "检测结果", path: "/app/results", icon: "Checked" },
          { label: "反馈管理", path: "/app/feedbacks", icon: "ChatLineRound" },
        ],
        show: () => true,
      });
    } else if (isUser.value || isExpert.value) {
      result.push({
        label: "",
        items: [
          { label: "任务管理", path: "/app/tasks", icon: "List" },
          { label: "检测结果", path: "/app/results", icon: "Checked" },
          { label: "反馈管理", path: "/app/feedbacks", icon: "ChatLineRound" },
        ],
        show: () => true,
      });
    }

    // Ops workspace items
    const opsItems: MenuItem[] = [];
    if (isAdmin.value || isAppDev.value || isPlatOp.value) {
      opsItems.push({ label: "Agent 管理", path: "/ops/agents", icon: "VideoPlay" });
    }
    if (isAdmin.value || isAppDev.value) {
      opsItems.push({ label: "Prompt 管理", path: "/ops/prompts", icon: "Edit" });
      opsItems.push({ label: "RAG 配置", path: "/ops/rag", icon: "DataAnalysis" });
    }
    if (isAdmin.value || isPlatOp.value || isAlgoEng.value) {
      opsItems.push({ label: "分析看板", path: "/ops/analytics", icon: "TrendCharts" });
    }
    if (isAdmin.value || isAppDev.value || isPlatOp.value) {
      opsItems.push({ label: "发布管理", path: "/ops/releases", icon: "Promotion" });
    }
    if (isAdmin.value) {
      opsItems.push({ label: "计费管理", path: "/ops/billing", icon: "Wallet" });
    }
    if (isAppDev.value) {
      opsItems.push({ label: "Agent 拓扑图", path: "/ops/agents/topology", icon: "Share" });
      opsItems.push({ label: "路由策略", path: "/ops/agents/intent-routes", icon: "Connection" });
      opsItems.push({ label: "DSPy 优化", path: "/ops/prompts/dspy", icon: "MagicStick" });
      opsItems.push({ label: "召回策略", path: "/ops/rag/policies", icon: "Search" });
      opsItems.push({ label: "流程节点", path: "/ops/workflows", icon: "SetUp" });
      opsItems.push({ label: "工具注册", path: "/ops/tools", icon: "Switch" });
    }
    if (isPlatOp.value) {
      opsItems.push({ label: "模板审核", path: "/ops/templates/review", icon: "DocumentChecked" });
      opsItems.push({ label: "模型版本", path: "/ops/models/versions", icon: "Box" });
      opsItems.push({ label: "调用监控", path: "/ops/models/monitor", icon: "Monitor" });
      opsItems.push({ label: "数据质量", path: "/ops/data-quality", icon: "Warning" });
      opsItems.push({ label: "标注任务", path: "/ops/label-tasks", icon: "EditPen" });
      opsItems.push({ label: "数据审核", path: "/ops/data-review", icon: "View" });
      opsItems.push({ label: "用户行为分析", path: "/ops/analytics/behavior", icon: "UserFilled" });
      opsItems.push({ label: "业务报表", path: "/ops/analytics/reports", icon: "Document" });
      opsItems.push({ label: "成本分析", path: "/ops/analytics/cost", icon: "Money" });
    }
    if (isAlgoEng.value) {
      opsItems.push({ label: "数据接入", path: "/ops/data/import", icon: "Upload" });
      opsItems.push({ label: "数据处理", path: "/ops/data/processing", icon: "Operation" });
      opsItems.push({ label: "测试集管理", path: "/ops/data/eval-sets", icon: "Files" });
      opsItems.push({ label: "训练任务", path: "/ops/training/jobs", icon: "Cpu" });
      opsItems.push({ label: "微调管理", path: "/ops/training/fine-tune", icon: "Setting" });
      opsItems.push({ label: "离线评测", path: "/ops/eval/offline", icon: "DocumentChecked" });
      opsItems.push({ label: "在线验证", path: "/ops/eval/online", icon: "Connection" });
      opsItems.push({ label: "实验追踪", path: "/ops/experiments", icon: "DataLine" });
      opsItems.push({ label: "部署记录", path: "/ops/deployments", icon: "Promotion" });
    }
    if (opsItems.length) {
      if (isAdmin.value) {
        result.push({ label: "运维工作台", workspace: "ops", items: opsItems, show: () => true });
      } else {
        result.push({ label: "", items: opsItems, show: () => true });
      }
    }

    // Governance workspace items
    const govItems: MenuItem[] = [];
    if (isAdmin.value) {
      govItems.push({ label: "用户管理", path: "/users", icon: "User" });
      govItems.push({ label: "角色与菜单", path: "/governance/admin/roles", icon: "Lock" });
      govItems.push({ label: "租户/组织", path: "/governance/admin/orgs", icon: "OfficeBuilding" });
      govItems.push({ label: "存储/基础设施", path: "/governance/admin/infrastructure", icon: "Monitor" });
      govItems.push({ label: "GPU 调度", path: "/governance/admin/gpu", icon: "Histogram" });
      govItems.push({ label: "登录日志", path: "/governance/admin/auth-logs", icon: "Notebook" });
      govItems.push({ label: "审计日志", path: "/governance/admin/audit-logs", icon: "Document" });
      govItems.push({ label: "高风险审批", path: "/governance/admin/approvals", icon: "Warning" });
    }
    if (isAdmin.value || isAlgoEng.value) {
      govItems.push({ label: "模型配置", path: "/governance/admin/models", icon: "Cpu" });
      govItems.push({ label: "检测标准", path: "/governance/admin/inspection-specs", icon: "Checked" });
    }
    if (isAdmin.value || isPlatOp.value || isAlgoEng.value) {
      govItems.push({ label: "质量报告", path: "/governance/quality/report", icon: "DataAnalysis" });
      govItems.push({ label: "质量追踪", path: "/governance/quality/tracing", icon: "Connection" });
      govItems.push({ label: "记忆治理", path: "/governance/memory", icon: "Management" });
    }
    if (govItems.length) {
      if (isAdmin.value) {
        result.push({ label: "治理工作台", workspace: "governance", items: govItems, show: () => true });
      } else {
        result.push({ label: "", items: govItems, show: () => true });
      }
    }

    // Profile (all roles)
    result.push({
      label: "",
      items: [{ label: "个人设置", path: "/app/profile", icon: "User" }],
      show: () => true,
    });

    return result;
  });

  return { sections, isAdmin };
}
```

- [ ] **Step 2: Rewrite AppLayout.vue sidebar template**

Replace the entire `<template>` sidebar section in `frontend/src/layouts/AppLayout.vue`:

The sidebar should:
1. Use `useMenu()` composable to get sections
2. For admin: render each section as `<el-collapse>` with workspace label
3. For non-admin: render flat menu items without collapse wrappers
4. `canChat` computed now checks for ROLE_USER or ROLE_EXPERT
5. `roleLabel` computed maps all 6 roles to Chinese labels

Replace the `canChat`, `canApp`, `canOps`, `canGovernance`, `canUserAdmin`, `roleLabel` computed properties with new logic using `useMenu()`.

Replace the `showChatControls` to work for both user and expert.

- [ ] **Step 3: Update AppLayout.vue script imports**

Remove old role imports, add new ones:
```typescript
import {
  ROLE_ADMIN,
  ROLE_USER,
  ROLE_EXPERT,
  WORKSPACE_GOVERNANCE,
  WORKSPACE_OPS,
} from "@/constants/roles";
```

Update `canChat`:
```typescript
const canChat = computed(() => {
  const pr = auth.primaryRole;
  return pr === ROLE_USER || pr === ROLE_EXPERT;
});
```

Update `roleLabel`:
```typescript
const roleLabel = computed(() => {
  switch (auth.primaryRole) {
    case ROLE_ADMIN: return "系统管理员";
    case ROLE_APP_DEVELOPER: return "应用开发者";
    case ROLE_PLATFORM_OPERATOR: return "平台运维员";
    case ROLE_ALGORITHM_ENGINEER: return "算法工程师";
    case ROLE_USER: return "用户";
    case ROLE_EXPERT: return "专家";
    default: return auth.role || "未识别角色";
  }
});
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/layouts/AppLayout.vue frontend/src/composables/useMenu.ts
git commit -m "feat: rewrite sidebar with role-based menu sections using useMenu composable

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 16: Update UserListView, DashboardView, ProfileView

**Files:**
- Modify: `frontend/src/views/UserListView.vue`
- Modify: `frontend/src/views/DashboardView.vue`
- Modify: `frontend/src/views/ProfileView.vue`

- [ ] **Step 1: Update UserListView.vue role imports and roleMeta**

Replace imports (lines 10-15):
```typescript
import {
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_PLATFORM_OPERATOR,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_USER,
  ROLE_EXPERT,
} from "@/constants/roles";
```

Replace `roleMeta` (lines 50-55):
```typescript
const roleMeta: Record<string, { label: string; type: string }> = {
  [ROLE_ADMIN]: { label: "系统管理员", type: "danger" },
  [ROLE_APP_DEVELOPER]: { label: "应用开发者", type: "warning" },
  [ROLE_PLATFORM_OPERATOR]: { label: "平台运维员", type: "warning" },
  [ROLE_ALGORITHM_ENGINEER]: { label: "算法工程师", type: "success" },
  [ROLE_USER]: { label: "用户", type: "info" },
  [ROLE_EXPERT]: { label: "专家", type: "" },
};
```

- [ ] **Step 2: Update DashboardView.vue isAdmin check**

```typescript
import { ROLE_ADMIN } from "@/constants/roles";
// ...
const isAdmin = computed(() => hasRole(ROLE_ADMIN));
```

- [ ] **Step 3: Update ProfileView.vue role display**

```typescript
import { ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER, ROLE_USER, ROLE_EXPERT } from "@/constants/roles";

const roleLabels: Record<string, string> = {
  [ROLE_ADMIN]: "系统管理员",
  [ROLE_APP_DEVELOPER]: "应用开发者",
  [ROLE_PLATFORM_OPERATOR]: "平台运维员",
  [ROLE_ALGORITHM_ENGINEER]: "算法工程师",
  [ROLE_USER]: "用户",
  [ROLE_EXPERT]: "专家",
};
// Use roleLabels[store.current.role] for display
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/UserListView.vue frontend/src/views/DashboardView.vue frontend/src/views/ProfileView.vue
git commit -m "feat: update views with 6 new role labels and checks

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 17: Create placeholder page component

**Files:**
- Create: `frontend/src/views/placeholder/PlaceholderView.vue`

- [ ] **Step 1: Create PlaceholderView.vue**

```vue
<template>
  <div class="flex flex-col items-center justify-center min-h-[60vh]">
    <el-icon class="text-5xl text-zinc-300 mb-4"><Tools /></el-icon>
    <h2 class="text-xl font-semibold text-zinc-500 mb-2">功能开发中</h2>
    <p class="text-sm text-zinc-400">{{ pageTitle }} 模块正在建设中，敬请期待。</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { Tools } from "@element-plus/icons-vue";

const route = useRoute();
const pageTitle = computed(() => (route.meta.title as string) || "该");
</script>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/placeholder/PlaceholderView.vue
git commit -m "feat: add placeholder page for unimplemented features

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 18: Fix backend test imports and assertions

**Files:**
- Modify: `backend/tests/test_agent_ops_api.py`
- Modify: `backend/tests/test_quality_agent_routing.py`
- Modify: Any other test files referencing old role constants

- [ ] **Step 1: Find all test files with old role references**

```bash
cd backend && grep -rn "ROLE_INSPECTOR\|ROLE_ANALYST\|ROLE_AGENT_OPERATOR\|ROLE_API_SERVICE\|normalize_role\|LEGACY_ROLE_MAP\|agent_operator\|inspector\|analyst" tests/ --include="*.py" -l
```

- [ ] **Step 2: Update each test file**

For each file found, replace old role imports and string references with new role constants. Key updates:

```python
# Old
from app.core.permissions import ROLE_AGENT_OPERATOR, ROLE_ANALYST, ...
# New
from app.core.permissions import ROLE_APP_DEVELOPER, ROLE_ALGORITHM_ENGINEER, ...
```

Update test assertions with new role values.

- [ ] **Step 3: Run backend tests**

```bash
cd backend && python -m pytest tests/ -x --timeout=30 2>&1 | tail -30
```
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test: update test imports and assertions for 6 new roles

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 19: Update admin views with new role checks

**Files:**
- Modify: `frontend/src/views/admin/InspectionSpecView.vue`
- Modify: Other admin views referencing roles

- [ ] **Step 1: Fix InspectionSpecView.vue imports**

Replace old role imports with `ROLE_ADMIN`, `ROLE_ALGORITHM_ENGINEER`.

- [ ] **Step 2: Fix any remaining old role references in frontend**

```bash
cd frontend && grep -rn "ROLE_INSPECTOR\|ROLE_ANALYST\|ROLE_AGENT_OPERATOR\|ROLE_API_SERVICE\|normalizeRole\|LEGACY_ROLE_MAP\|agent_operator\|inspector\b\|analyst\b" src/ --include="*.ts" --include="*.vue" -l
```

Fix all remaining occurrences.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat: fix all remaining old role references in frontend

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 20: Final system verification

- [ ] **Step 1: Verify no old role names remain**

```bash
cd backend && grep -rn "inspector\|analyst\|agent_operator\|super_admin\|org_admin\|platform_admin\|auditor\|viewer\|ai_quality" app/ --include="*.py" | grep -v "algorithm_engineer\|\.pyc" | grep -v "test_"
```
Expected: No output (or only in migration history / data files that are intentionally tracking historical role mappings).

```bash
cd frontend && grep -rn "inspector\|analyst\|agent_operator\|normalizeRole\|LEGACY_ROLE_MAP" src/ --include="*.ts" --include="*.vue"
```
Expected: No output.

- [ ] **Step 2: Verify backend tests pass**

```bash
cd backend && python -m pytest tests/ -v --timeout=30 2>&1 | tail -20
```
Expected: All tests pass.

- [ ] **Step 3: Verify frontend compiles**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | tail -20
```
Expected: No type errors.

- [ ] **Step 4: Commit any remaining changes**

```bash
git status
git add -A
git commit -m "chore: final verification cleanup for 6-role unification

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Summary

| Task | Scope | Files |
|------|-------|-------|
| 1 | Backend role constants | `permissions.py` |
| 2 | Claims derivation | `claims.py` |
| 3 | Domain enum | `domain/user.py` |
| 4 | Defaults | `models/user.py`, `schemas/user.py` |
| 5 | Services | `user_service.py`, `inspection_spec_service.py`, `chat_service.py`, `task_service.py`, `billing_service.py` |
| 6 | API layer | `deps.py`, all `api/v1/*.py` |
| 7 | DB migration | `migrations/versions/0022_*.py` |
| 8 | Seed data | `migrations/data/0021_*.json` |
| 9 | Frontend constants | `constants/roles.ts` |
| 10 | Auth + permission | `auth.store.ts`, `usePermission.ts` |
| 11 | Router guard | `router/index.ts` |
| 12 | App routes | `routes/app.routes.ts` |
| 13 | Ops routes | `routes/ops.routes.ts` |
| 14 | Governance routes | `routes/governance.routes.ts` |
| 15 | Sidebar | `layouts/AppLayout.vue`, `composables/useMenu.ts` |
| 16 | Views | `UserListView.vue`, `DashboardView.vue`, `ProfileView.vue` |
| 17 | Placeholder | `views/placeholder/PlaceholderView.vue` |
| 18 | Backend tests | `tests/*.py` |
| 19 | Frontend cleanup | remaining old role references |
| 20 | Verification | Full system check |
