from __future__ import annotations

from typing import Dict, Set

from app.core.exceptions import ForbiddenError, ValidationError


ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_INSPECTOR = "inspector"
ROLE_ANALYST = "analyst"
ROLE_AGENT_OPERATOR = "agent_operator"
ROLE_API_SERVICE = "api_service"

ALL_ROLES = {
    ROLE_ADMIN,
    ROLE_USER,
    ROLE_INSPECTOR,
    ROLE_ANALYST,
    ROLE_AGENT_OPERATOR,
    ROLE_API_SERVICE,
}

LEGACY_ROLE_MAP = {
    "super_admin": ROLE_ADMIN,
    "org_admin": ROLE_ADMIN,
    "platform_admin": ROLE_ADMIN,
    "auditor": ROLE_ADMIN,
    "viewer": ROLE_INSPECTOR,
    "ai_quality": ROLE_ANALYST,
}

PERMISSIONS: Dict[str, Set[str]] = {
    "user": {ROLE_ADMIN},
    "task": {ROLE_ADMIN, ROLE_USER, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_AGENT_OPERATOR, ROLE_API_SERVICE},
    "result": {ROLE_ADMIN, ROLE_USER, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_AGENT_OPERATOR, ROLE_API_SERVICE},
    "stability": {ROLE_ADMIN, ROLE_USER, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_AGENT_OPERATOR, ROLE_API_SERVICE},
    "alert": {ROLE_ADMIN, ROLE_USER, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_AGENT_OPERATOR, ROLE_API_SERVICE},
    "tool": {ROLE_ADMIN, ROLE_USER, ROLE_INSPECTOR, ROLE_AGENT_OPERATOR, ROLE_API_SERVICE},
    "analytics": {ROLE_ADMIN, ROLE_USER, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_AGENT_OPERATOR, ROLE_API_SERVICE},
    "audit": {ROLE_ADMIN},
    "model_config": {ROLE_ADMIN},
    "inspection_spec": {ROLE_ADMIN, ROLE_USER, ROLE_ANALYST},
    "billing": {ROLE_ADMIN},
    "feedback": {ROLE_ADMIN, ROLE_USER, ROLE_INSPECTOR, ROLE_ANALYST},
    "quality": {ROLE_ADMIN, ROLE_USER, ROLE_ANALYST},
    "agent_ops": {ROLE_ADMIN, ROLE_AGENT_OPERATOR},
    "chat": {ROLE_ADMIN, ROLE_USER, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_AGENT_OPERATOR, ROLE_API_SERVICE},
}


def require_role(resource: str, role: str) -> None:
    normalized = LEGACY_ROLE_MAP.get(role, role)
    allowed = PERMISSIONS.get(resource, set())
    if normalized not in allowed:
        raise ForbiddenError(f"role {role} cannot access {resource}")


def ensure_valid_role(role: str) -> None:
    normalized = LEGACY_ROLE_MAP.get(role, role)
    if normalized not in ALL_ROLES:
        raise ValidationError(f"invalid role: {role}")


def normalize_role(role: str) -> str:
    return LEGACY_ROLE_MAP.get(role, role)
