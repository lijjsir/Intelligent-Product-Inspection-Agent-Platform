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

ROLE_LABELS = {
    ROLE_ADMIN: "管理员", ROLE_EXPERT: "领域专家", ROLE_USER: "普通用户",
    ROLE_ALGORITHM_ENGINEER: "算法工程师", ROLE_APP_DEVELOPER: "应用开发者", ROLE_PLATFORM_OPERATOR: "平台运营",
}

# Display and pagination use the same role order, independent of creation time.
ROLE_DISPLAY_ORDER = [ROLE_ADMIN, ROLE_EXPERT, ROLE_USER, ROLE_ALGORITHM_ENGINEER,
                      ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR]

ROLE_RESTRICTED_PERMISSIONS = {
    ROLE_USER: {"inspection_spec_read", "inspection_spec", "inspection_standard_library_read", "inspection_standard_library", "product_master_read", "product_master"},
    ROLE_ALGORITHM_ENGINEER: {"task"},
}

# A professional may be delegated publication rights, but review is their default duty.
DEFAULT_EXCLUDED_PERMISSIONS = {ROLE_EXPERT: {"standard_admission_publish"}}

PERMISSIONS: Dict[str, Set[str]] = {
    "user": {ROLE_ADMIN},
    "task": {ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR},
    "result": {ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR},
    "stability": {ROLE_EXPERT, ROLE_PLATFORM_OPERATOR},
    "alert": {ROLE_ADMIN, ROLE_PLATFORM_OPERATOR},
    "alert_rule_read": {ROLE_ADMIN, ROLE_PLATFORM_OPERATOR},
    "alert_rule": {ROLE_ADMIN, ROLE_PLATFORM_OPERATOR},
    "tool": {ROLE_ADMIN, ROLE_APP_DEVELOPER},
    "analytics": {ROLE_ADMIN, ROLE_PLATFORM_OPERATOR},
    "audit": {ROLE_ADMIN},
    "model_config": {ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER},
    "model_config_read": {ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER, ROLE_PLATFORM_OPERATOR},
    "gpu_infra": {ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER},
    "inspection_spec_read": {
        ROLE_ADMIN,
        ROLE_APP_DEVELOPER,
        ROLE_PLATFORM_OPERATOR,
        ROLE_ALGORITHM_ENGINEER,
        ROLE_USER,
        ROLE_EXPERT,
    },
    "inspection_spec": {ROLE_ADMIN},
    "inspection_standard_library_read": {
        ROLE_ADMIN,
        ROLE_APP_DEVELOPER,
        ROLE_PLATFORM_OPERATOR,
        ROLE_ALGORITHM_ENGINEER,
        ROLE_USER,
        ROLE_EXPERT,
    },
    "inspection_standard_library": {ROLE_ADMIN},
    "standard_admission_submit": {ROLE_ADMIN, ROLE_EXPERT},
    "standard_admission_review": {ROLE_EXPERT},
    "standard_admission_publish": {ROLE_ADMIN, ROLE_EXPERT},
    "standard_review_assign": {ROLE_ADMIN},
    "product_master_read": {ROLE_ADMIN},
    "product_master": {ROLE_ADMIN},
    "billing": {ROLE_ADMIN},
    "feedback": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER, ROLE_USER, ROLE_EXPERT},
    "report_generate": {ROLE_ADMIN, ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR},
    "report_read": {ROLE_ADMIN, ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR},
    "quality": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER, ROLE_EXPERT},
    "quality_delete": {ROLE_ADMIN},
    "quality_material_submit": {ROLE_ADMIN, ROLE_EXPERT, ROLE_USER},
    "quality_material_read_own": {ROLE_ADMIN, ROLE_EXPERT, ROLE_USER},
    "quality_material_read_business": {ROLE_ADMIN, ROLE_EXPERT},
    "quality_ingestion_manage": {ROLE_ADMIN, ROLE_EXPERT, ROLE_USER},
    "agent_ops_read": {ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR},
    "agent_ops": {ROLE_ADMIN, ROLE_APP_DEVELOPER},
    "prompt_admin": {ROLE_ADMIN, ROLE_APP_DEVELOPER},
    "chat": {ROLE_USER, ROLE_EXPERT},
    "collab": {
        ROLE_ADMIN,
        ROLE_APP_DEVELOPER,
        ROLE_PLATFORM_OPERATOR,
        ROLE_ALGORITHM_ENGINEER,
        ROLE_EXPERT,
    },
    "dataset": {ROLE_ALGORITHM_ENGINEER},
    "algo_workspace": {ROLE_ALGORITHM_ENGINEER},
    "meeting": {
        ROLE_ADMIN,
        ROLE_APP_DEVELOPER,
        ROLE_PLATFORM_OPERATOR,
        ROLE_ALGORITHM_ENGINEER,
        ROLE_EXPERT,
    },
    "meeting_admin": {ROLE_ADMIN},
    "organization": {ROLE_ADMIN},
    "role_read": {ROLE_ADMIN},
    "auth_log": {ROLE_ADMIN},
    "audit_log": {ROLE_ADMIN},
    "infrastructure": {ROLE_ADMIN},
    "memory_governance": {ROLE_ADMIN},
    "memory_policy": {ROLE_ADMIN},
    "knowledge_candidate_submit": {ROLE_ADMIN,ROLE_EXPERT,ROLE_USER},
    "knowledge_read": {ROLE_ADMIN,ROLE_EXPERT},
    "knowledge_review": {ROLE_EXPERT},
    "knowledge_share_decide": {ROLE_ADMIN},
    "knowledge_publish": {ROLE_ADMIN,ROLE_EXPERT},
    "inspection_execution": {ROLE_USER,ROLE_EXPERT},
    "inspection_execution_review": {ROLE_EXPERT},
    "approval": {ROLE_ADMIN},
    "approval_read": {
        ROLE_ADMIN,
        ROLE_ALGORITHM_ENGINEER,
        ROLE_APP_DEVELOPER,
        ROLE_PLATFORM_OPERATOR,
    },
    "approval_create": {
        ROLE_ADMIN,
        ROLE_ALGORITHM_ENGINEER,
        ROLE_APP_DEVELOPER,
        ROLE_PLATFORM_OPERATOR,
    },
}


for _allowed_roles in PERMISSIONS.values():
    _allowed_roles.add(ROLE_ADMIN)
PERMISSIONS["standard_admission_review"].discard(ROLE_ADMIN)
PERMISSIONS["knowledge_review"].discard(ROLE_ADMIN)
PERMISSIONS["inspection_execution_review"].discard(ROLE_ADMIN)
for _resource, _allowed_roles in PERMISSIONS.items():
    if _resource in ROLE_RESTRICTED_PERMISSIONS[ROLE_USER]:
        _allowed_roles.discard(ROLE_USER)

PERMISSION_DEPENDENCIES = {"report_generate": {"task", "result", "report_read"}, "report_read": {"task", "result"}}
for _standard_action in {"standard_admission_submit", "standard_admission_review", "standard_admission_publish"}:
    PERMISSION_DEPENDENCIES[_standard_action] = {"inspection_standard_library_read"}


class PermissionRole(str):
    """A role name carrying a fresh, organization-scoped authorization snapshot.

    Keep existing role comparisons and service calls compatible while making all
    require_role checks use the effective permissions loaded for this request.
    """

    def __new__(cls, role: str, resources: list[str]):
        instance = super().__new__(cls, role)
        instance.resources = frozenset(resources)
        return instance

    def __getnewargs__(self):
        return str(self), list(self.resources)


def assignable_permissions(role: str) -> frozenset[str]:
    """Fixed role boundary, independent of mutable organization grants."""
    restricted = ROLE_RESTRICTED_PERMISSIONS.get(role, set())
    return frozenset(resource for resource, roles in PERMISSIONS.items()
                     if role in roles and resource not in restricted)


def has_permission(resource: str, role: str) -> bool:
    if resource not in PERMISSIONS:
        return False
    if resource in {"standard_admission_review","knowledge_review","inspection_execution_review"} and str(role) != ROLE_EXPERT:
        return False
    if role == ROLE_ADMIN:
        return True
    if resource not in assignable_permissions(role):
        return False
    if isinstance(role, PermissionRole):
        return resource in role.resources and PERMISSION_DEPENDENCIES.get(resource, set()) <= role.resources
    return role in PERMISSIONS.get(resource, set()) and resource not in DEFAULT_EXCLUDED_PERMISSIONS.get(role, set())


def require_role(resource: str, role: str) -> None:
    if not has_permission(resource, role):
        raise ForbiddenError(f"role {role} cannot access {resource}")


def ensure_valid_role(role: str) -> None:
    if role not in ALL_ROLES:
        raise ValidationError(f"invalid role: {role}")
