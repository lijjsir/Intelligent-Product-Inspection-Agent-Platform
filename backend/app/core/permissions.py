from __future__ import annotations

from typing import Dict, Set

from app.core.exceptions import ForbiddenError, ValidationError


ROLE_SUPER_ADMIN = "super_admin"
ROLE_ORG_ADMIN = "org_admin"
ROLE_INSPECTOR = "inspector"
ROLE_VIEWER = "viewer"
ROLE_ANALYST = "analyst"
ROLE_API_SERVICE = "api_service"
ROLE_AUDITOR = "auditor"
ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_AI_QUALITY = "ai_quality"
ROLE_AGENT_OPERATOR = "agent_operator"

ALL_ROLES = {
    ROLE_SUPER_ADMIN,
    ROLE_ORG_ADMIN,
    ROLE_INSPECTOR,
    ROLE_VIEWER,
    ROLE_ANALYST,
    ROLE_API_SERVICE,
    ROLE_AUDITOR,
    ROLE_PLATFORM_ADMIN,
    ROLE_AI_QUALITY,
    ROLE_AGENT_OPERATOR,
}

PERMISSIONS: Dict[str, Set[str]] = {
    "user": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN},
    "task": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR, ROLE_VIEWER, ROLE_AGENT_OPERATOR},
    "result": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_VIEWER, ROLE_AGENT_OPERATOR},
    "stability": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_VIEWER, ROLE_AGENT_OPERATOR},
    "alert": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_VIEWER, ROLE_AGENT_OPERATOR},
    "tool": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR, ROLE_AGENT_OPERATOR},
    "analytics": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_ANALYST, ROLE_VIEWER, ROLE_AGENT_OPERATOR},
    "audit": {ROLE_SUPER_ADMIN, ROLE_AUDITOR},
    "model_config": {ROLE_SUPER_ADMIN, ROLE_PLATFORM_ADMIN},
    "inspection_spec": {ROLE_SUPER_ADMIN, ROLE_PLATFORM_ADMIN, ROLE_AI_QUALITY, ROLE_ORG_ADMIN},
    "billing": {ROLE_SUPER_ADMIN, ROLE_PLATFORM_ADMIN, ROLE_ORG_ADMIN},
    "feedback": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR, ROLE_ANALYST, ROLE_AI_QUALITY},
    "quality": {ROLE_SUPER_ADMIN, ROLE_AI_QUALITY},
}


def require_role(resource: str, role: str) -> None:
    allowed = PERMISSIONS.get(resource, set())
    if role not in allowed:
        raise ForbiddenError(f"role {role} cannot access {resource}")


def ensure_valid_role(role: str) -> None:
    if role not in ALL_ROLES:
        raise ValidationError(f"invalid role: {role}")
