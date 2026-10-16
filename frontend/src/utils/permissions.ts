import type { PermissionAction, PermissionEffect } from "@/types/permission.types";
import type { User } from "@/types/user.types";
import type { RoleItem } from "@/types/governance.types";

export function groupUsersByRole(
  users: User[],
  roles: RoleItem[],
  counts: Record<string, number>,
  filter = "",
) {
  return roles
    .filter(
      (role) =>
        (!filter || role.key === filter) &&
        (counts[role.key] || users.some((user) => user.role === role.key)),
    )
    .map((role) => ({
      ...role,
      count: counts[role.key] || 0,
      users: users
        .filter((user) => user.role === role.key)
        .sort(
          (a, b) =>
            a.username.localeCompare(b.username, "zh-CN", { numeric: true }) ||
            a.id.localeCompare(b.id),
        ),
    }));
}

export function resolvePermissions(
  defaults: string[],
  overrides: Record<string, PermissionEffect>,
  dependencies: Record<string, string[]> = {},
): string[] {
  const result = new Set(defaults);
  for (const [key, effect] of Object.entries(overrides)) {
    if (effect === "grant") result.add(key);
    else if (effect === "deny") result.delete(key);
  }
  return [...result]
    .filter((key) => (dependencies[key] || []).every((required) => result.has(required)))
    .sort();
}

export function personalPermissionToggle(
  overrides: Record<string, PermissionEffect>,
  key: string,
  allowed: boolean,
) {
  const next = { ...overrides };
  next[key] = allowed ? "grant" : "deny";
  return next;
}

export function permissionDifference(before: string[], after: string[]) {
  return {
    granted: after.filter((key) => !before.includes(key)),
    revoked: before.filter((key) => !after.includes(key)),
  };
}

export function personalGrantOptions(
  catalog: PermissionAction[],
  defaults: string[],
  overrides: Record<string, PermissionEffect>,
  dependencies: Record<string, string[]> = {},
) {
  const effective = new Set(resolvePermissions(defaults, overrides, dependencies));
  return {
    extra: catalog.filter(
      (action) => !defaults.includes(action.key) && overrides[action.key] !== "grant",
    ),
    restore: catalog.filter(
      (action) => defaults.includes(action.key) && !effective.has(action.key),
    ),
    fixed: catalog.filter(
      (action) =>
        defaults.includes(action.key) &&
        effective.has(action.key) &&
        overrides[action.key] !== "grant",
    ),
  };
}

export function groupPermissionFeatures(catalog: PermissionAction[]) {
  const features = new Map<
    string,
    { id: string; name: string; group: string; actions: PermissionAction[] }
  >();
  for (const action of catalog) {
    const id = `${action.group}:${action.name}`;
    if (!features.has(id))
      features.set(id, { id, name: action.name, group: action.group, actions: [] });
    features.get(id)!.actions.push(action);
  }
  return [...features.values()];
}

export function rolePermissionCatalog(catalog: PermissionAction[], allowed: string[], role = "") {
  const scope = new Set(allowed);
  return catalog
    .filter((action) => scope.has(action.key))
    .map((action) => ({ ...action, ...action.role_presentation?.[role] }));
}

export function samePermissions(left: string[], right: string[]) {
  return JSON.stringify([...left].sort()) === JSON.stringify([...right].sort());
}

export function sameOverrides(
  left: Record<string, PermissionEffect>,
  right: Record<string, PermissionEffect>,
) {
  const entries = (value: Record<string, PermissionEffect>) =>
    Object.entries(value).sort(([a], [b]) => a.localeCompare(b));
  return JSON.stringify(entries(left)) === JSON.stringify(entries(right));
}
