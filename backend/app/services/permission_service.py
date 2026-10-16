from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permission_catalog import GROUPS, permission_catalog
from app.core.permissions import ALL_ROLES, PERMISSIONS, PERMISSION_DEPENDENCIES, ROLE_ADMIN, ROLE_LABELS, ROLE_RESTRICTED_PERMISSIONS, DEFAULT_EXCLUDED_PERMISSIONS, assignable_permissions, ensure_valid_role
from app.models.organization import Organization
from app.models.permission import RolePermission, UserPermission
from app.models.user import User
from app.schemas.permission import RolePermissionUpdate, UserPermissionUpdate
from app.schemas.user import CurrentUser
from app.services.audit_service import AuditService


def default_permissions(role: str) -> list[str]:
    return sorted(assignable_permissions(role) - DEFAULT_EXCLUDED_PERMISSIONS.get(role, set()))


def effective_permissions(defaults: list[str], overrides: dict[str, str]) -> list[str]:
    granted = {key for key, effect in overrides.items() if effect == "grant"}
    denied = {key for key, effect in overrides.items() if effect == "deny"}
    result = ((set(defaults) | granted) - denied) & PERMISSIONS.keys()
    return sorted(key for key in result if PERMISSION_DEPENDENCIES.get(key, set()) <= result)


class PermissionService:
    def __init__(self, session: AsyncSession, org_id: str):
        self.session = session
        self.org_id = org_id

    async def _user(self, user_id: str, *, lock: bool = False) -> User:
        statement = select(User).where(
            User.id == user_id, User.org_id == self.org_id, User.deleted_at.is_(None),
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        user = (await self.session.execute(statement)).scalar_one_or_none()
        if not user:
            raise NotFoundError("用户不存在或不属于当前组织")
        return user

    async def _lock_organization(self):
        # Serialize initial inserts as well as updates; absent grant rows cannot
        # be locked. Authorization changes and their audit records commit together.
        org = (await self.session.execute(select(Organization).where(
            Organization.id == self.org_id, Organization.deleted_at.is_(None),
        ).with_for_update())).scalar_one_or_none()
        if not org:
            raise NotFoundError("组织不存在")

    @staticmethod
    def _require_admin(actor: CurrentUser):
        if actor.role != ROLE_ADMIN:
            raise ForbiddenError("仅管理员可以修改角色和个人授权")

    @staticmethod
    def _validate_resources(resources):
        unknown = set(resources) - PERMISSIONS.keys()
        if unknown:
            raise ValidationError(f"未知权限：{', '.join(sorted(unknown))}")

    @staticmethod
    def _validate_role_scope(role: str, resources):
        outside = set(resources) - assignable_permissions(role)
        if outside:
            raise ValidationError(f"不能为{ROLE_LABELS.get(role, role)}授予职责范围之外的权限，请选择对应角色后再授权。",
                                  detail={"role": role, "resources": sorted(outside)})

    async def matrix(self) -> dict:
        saved = {row.role: row for row in (await self.session.execute(
            select(RolePermission).where(RolePermission.org_id == self.org_id)
        )).scalars()}
        return {
            "resources": sorted(PERMISSIONS),
            "matrix": {role: (effective_permissions(sorted(set(saved[role].resources) & assignable_permissions(role)), {}) if role in saved and role != ROLE_ADMIN
                              else default_permissions(role)) for role in sorted(ALL_ROLES)},
            "versions": {role: saved[role].version if role in saved else 0 for role in ALL_ROLES},
            "catalog": permission_catalog(), "groups": GROUPS, "protected_roles": [ROLE_ADMIN],
            "role_restrictions": {role: sorted(resources) for role, resources in ROLE_RESTRICTED_PERMISSIONS.items()},
            "role_capabilities": {role: sorted(assignable_permissions(role)) for role in sorted(ALL_ROLES)},
        }

    async def user_permissions(self, user_id: str) -> dict:
        user = await self._user(user_id)
        role = await self.session.get(RolePermission, (self.org_id, user.role))
        adjustment = await self.session.get(UserPermission, (self.org_id, user.id))
        defaults = (role.resources if role and user.role != ROLE_ADMIN else default_permissions(user.role))
        overrides = adjustment.overrides if adjustment and user.role != ROLE_ADMIN else {}
        allowed = assignable_permissions(user.role)
        defaults = sorted(set(defaults) & allowed)
        overrides = {key: effect for key, effect in overrides.items() if key in allowed}
        return {
            "user_id": user.id, "username": user.username, "role": user.role,
            "role_default": sorted(defaults), "overrides": dict(overrides),
            "role_version": role.version if role else 0,
            "effective": effective_permissions(defaults, overrides),
            "version": adjustment.version if adjustment else 0,
            "is_active": user.is_active,
        }

    async def identity(self, user_id: str) -> dict:
        org = await self.session.get(Organization, self.org_id)
        if not org or not org.is_active or org.deleted_at:
            raise ForbiddenError("组织不存在或已停用")
        data = await self.user_permissions(user_id)
        if not data["is_active"]:
            raise ForbiddenError("账号已停用")
        return data

    async def save_role(self, role: str, payload: RolePermissionUpdate, actor: CurrentUser) -> dict:
        self._require_admin(actor)
        ensure_valid_role(role)
        self._validate_resources(payload.resources)
        self._validate_role_scope(role, payload.resources)
        if role == ROLE_ADMIN:
            raise ForbiddenError("管理员的内置权限受保护")
        await self._lock_organization()
        row = (await self.session.execute(select(RolePermission).where(
            RolePermission.org_id == self.org_id, RolePermission.role == role,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if (row.version if row else 0) != payload.version:
            raise ConflictError("角色权限已被其他管理员修改，请刷新后重新编辑")
        before = row.resources if row else default_permissions(role)
        if row is None:
            row = RolePermission(org_id=self.org_id, role=role, resources=[], version=0)
            self.session.add(row)
        row.resources = sorted(set(payload.resources))
        row.version += 1
        await self._audit(actor, "role_permissions", None, {"role": role, "before": before, "after": row.resources})
        await self.session.flush()
        return await self.matrix()

    async def save_user(self, user_id: str, payload: UserPermissionUpdate, actor: CurrentUser) -> dict:
        self._require_admin(actor)
        ensure_valid_role(payload.role)
        self._validate_resources(payload.overrides)
        self._validate_role_scope(payload.role, payload.overrides)
        await self._lock_organization()
        user = await self._user(user_id, lock=True)
        if user.role == ROLE_ADMIN:
            raise ForbiddenError("管理员账号的授权受保护")
        if payload.role == ROLE_ADMIN and payload.overrides:
            raise ValidationError("分配管理员角色时不能设置个人调整")
        row = (await self.session.execute(select(UserPermission).where(
            UserPermission.org_id == self.org_id, UserPermission.user_id == user_id,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if user.role != payload.expected_role or (row.version if row else 0) != payload.version:
            raise ConflictError("用户授权已被其他管理员修改，请刷新后重新编辑")
        before = {"role": user.role, "overrides": dict(row.overrides) if row else {}}
        if row is None:
            row = UserPermission(org_id=self.org_id, user_id=user_id, overrides={}, version=0)
            self.session.add(row)
        user.role = payload.role
        row.overrides = dict(payload.overrides)
        row.version += 1
        await self._audit(actor, "user_permissions", user_id, {"before": before, "after": {
            "role": user.role, "overrides": row.overrides,
        }})
        await self.session.flush()
        return await self.user_permissions(user_id)

    async def _audit(self, actor, resource_type, resource_id, changes):
        await AuditService(self.session).write_outbox({
            "org_id": self.org_id, "actor_id": actor.user_id, "actor_role": str(actor.role),
            "resource_type": resource_type, "resource_id": resource_id, "action": "update",
            "changes": changes,
        })
