from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.permissions import (
    ROLE_ADMIN,
    ROLE_AGENT_OPERATOR,
    ROLE_ANALYST,
    ROLE_INSPECTOR,
    ROLE_USER,
    normalize_role,
)


WORKSPACE_APP = "app"
WORKSPACE_OPS = "ops"
WORKSPACE_GOVERNANCE = "governance"

PLAN_BASIC = "basic"
PLAN_PREMIUM = "premium"
PLAN_ENTERPRISE = "enterprise"

CAPABILITY_PRIVATE_RAG = "private_rag"
CAPABILITY_CUSTOM_WORKFLOW = "custom_workflow"
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
    capabilities = {CAPABILITY_PRIVATE_RAG}
    if plan_tier in {PLAN_PREMIUM, PLAN_ENTERPRISE}:
        capabilities.add(CAPABILITY_CUSTOM_WORKFLOW)
        capabilities.add(CAPABILITY_ADVANCED_ANALYTICS)
    if plan_tier == PLAN_ENTERPRISE:
        capabilities.add(CAPABILITY_MODEL_CONTROL)
    normalized = [normalize_role(r) for r in roles]
    if any(role in {ROLE_ADMIN, ROLE_ANALYST} for role in normalized):
        capabilities.add(CAPABILITY_GOVERNANCE)
        capabilities.add(CAPABILITY_MODEL_CONTROL)
    return sorted(capabilities)


def derive_workspaces(roles: list[str]) -> list[str]:
    workspaces: list[str] = []
    normalized = [normalize_role(r) for r in roles]
    if any(role in {ROLE_USER, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_ADMIN} for role in normalized):
        workspaces.append(WORKSPACE_APP)
    if any(role in {ROLE_AGENT_OPERATOR, ROLE_ADMIN} for role in normalized):
        workspaces.append(WORKSPACE_OPS)
    if any(role in {ROLE_ADMIN, ROLE_ANALYST} for role in normalized):
        workspaces.append(WORKSPACE_GOVERNANCE)
    if not workspaces:
        workspaces.append(WORKSPACE_APP)
    return workspaces


def derive_default_workspace(roles: list[str], workspaces: list[str]) -> str:
    normalized = [normalize_role(r) for r in roles]
    if ROLE_ADMIN in normalized:
        return WORKSPACE_GOVERNANCE
    if ROLE_ANALYST in normalized:
        return WORKSPACE_GOVERNANCE
    if ROLE_AGENT_OPERATOR in normalized:
        return WORKSPACE_OPS
    return workspaces[0]


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
