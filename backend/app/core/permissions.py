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
    "task": {ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR},
    "result": {ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR},
    "stability": {ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR},
    "alert": {ROLE_PLATFORM_OPERATOR},
    "alert_rule": {ROLE_PLATFORM_OPERATOR},
    "tool": {ROLE_APP_DEVELOPER},
    "analytics": {ROLE_PLATFORM_OPERATOR},
    "audit": {ROLE_ADMIN},
    "model_config": {ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER},
    "model_config_read": {ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER, ROLE_PLATFORM_OPERATOR},
    "inspection_spec_read": {
        ROLE_ADMIN,
        ROLE_APP_DEVELOPER,
        ROLE_PLATFORM_OPERATOR,
        ROLE_ALGORITHM_ENGINEER,
        ROLE_USER,
        ROLE_EXPERT,
    },
    "inspection_spec": {ROLE_ADMIN},
    "billing": {ROLE_ADMIN},
    "feedback": {ROLE_USER, ROLE_EXPERT},
    "quality": {ROLE_ADMIN, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER},
    "agent_ops": {ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR},
    "chat": {ROLE_USER, ROLE_EXPERT},
    "meeting": {ROLE_USER, ROLE_EXPERT},
}


def require_role(resource: str, role: str) -> None:
    allowed = PERMISSIONS.get(resource, set())
    if role not in allowed:
        raise ForbiddenError(f"role {role} cannot access {resource}")


def ensure_valid_role(role: str) -> None:
    if role not in ALL_ROLES:
        raise ValidationError(f"invalid role: {role}")
