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
    "inspection_spec_read": {
        ROLE_ADMIN,
        ROLE_APP_DEVELOPER,
        ROLE_PLATFORM_OPERATOR,
        ROLE_ALGORITHM_ENGINEER,
        ROLE_USER,
        ROLE_EXPERT,
    },
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
