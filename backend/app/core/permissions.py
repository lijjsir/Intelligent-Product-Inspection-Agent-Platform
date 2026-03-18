from __future__ import annotations

from typing import Dict, Set

from app.core.exceptions import ForbiddenError, ValidationError


ROLE_SUPER_ADMIN = "super_admin"
ROLE_ORG_ADMIN = "org_admin"
ROLE_INSPECTOR = "inspector"
ROLE_ANALYST = "analyst"
ROLE_API_SERVICE = "api_service"
ROLE_AUDITOR = "auditor"

ALL_ROLES = {
    ROLE_SUPER_ADMIN,
    ROLE_ORG_ADMIN,
    ROLE_INSPECTOR,
    ROLE_ANALYST,
    ROLE_API_SERVICE,
    ROLE_AUDITOR,
}

PERMISSIONS: Dict[str, Set[str]] = {
    "user": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN},
    "task": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR},
    "result": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR, ROLE_ANALYST},
    "stability": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR, ROLE_ANALYST},
    "alert": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR, ROLE_ANALYST},
    "tool": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_INSPECTOR},
    "analytics": {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_ANALYST},
    "audit": {ROLE_SUPER_ADMIN, ROLE_AUDITOR},
}


def require_role(resource: str, role: str) -> None:
    allowed = PERMISSIONS.get(resource, set())
    if role not in allowed:
        raise ForbiddenError(f"role {role} cannot access {resource}")


def ensure_valid_role(role: str) -> None:
    if role not in ALL_ROLES:
        raise ValidationError(f"invalid role: {role}")
