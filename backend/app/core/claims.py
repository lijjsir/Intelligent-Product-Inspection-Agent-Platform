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
    if ROLE_ADMIN in roles:
        capabilities.add(CAPABILITY_GOVERNANCE)
        capabilities.add(CAPABILITY_MODEL_CONTROL)
        capabilities.add(CAPABILITY_ADVANCED_ANALYTICS)
    if ROLE_APP_DEVELOPER in roles:
        capabilities.add(CAPABILITY_PRIVATE_RAG)
        capabilities.add(CAPABILITY_CUSTOM_PROMPT)
        capabilities.add(CAPABILITY_CUSTOM_WORKFLOW)
    if ROLE_PLATFORM_OPERATOR in roles:
        capabilities.add(CAPABILITY_ADVANCED_ANALYTICS)
    if ROLE_ALGORITHM_ENGINEER in roles:
        capabilities.add(CAPABILITY_COT_CONTROL)
        capabilities.add(CAPABILITY_MODEL_CONTROL)
        capabilities.add(CAPABILITY_ADVANCED_ANALYTICS)
    if ROLE_EXPERT in roles:
        capabilities.add(CAPABILITY_PRIVATE_RAG)
        capabilities.add(CAPABILITY_CUSTOM_PROMPT)
    if plan_tier in {PLAN_PREMIUM, PLAN_ENTERPRISE} and any(r in {ROLE_USER, ROLE_EXPERT} for r in roles):
        capabilities.add(CAPABILITY_PRIVATE_RAG)
    return sorted(capabilities)


def derive_workspaces(roles: list[str]) -> list[str]:
    workspaces: list[str] = []
    if any(r in {ROLE_USER, ROLE_EXPERT} for r in roles):
        workspaces.append(WORKSPACE_APP)
    if any(r in {ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER} for r in roles):
        workspaces.append(WORKSPACE_OPS)
    if ROLE_ADMIN in roles:
        workspaces.append(WORKSPACE_GOVERNANCE)
    if not workspaces:
        workspaces.append(WORKSPACE_APP)
    return workspaces


def derive_default_workspace(roles: list[str], workspaces: list[str]) -> str:
    if ROLE_ADMIN in roles:
        return WORKSPACE_GOVERNANCE
    if ROLE_APP_DEVELOPER in roles:
        return WORKSPACE_OPS
    if ROLE_PLATFORM_OPERATOR in roles:
        return WORKSPACE_OPS
    if ROLE_ALGORITHM_ENGINEER in roles:
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
