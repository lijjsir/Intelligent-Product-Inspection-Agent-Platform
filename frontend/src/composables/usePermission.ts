import { useAuthStore } from "@/stores/auth.store";
import { ROLE_ADMIN, normalizeRole } from "@/constants/roles";

export function usePermission() {
  const auth = useAuthStore();

  function hasRole(requiredRole: string | string[]): boolean {
    if (!auth.isAuthed) return false;
    const currentRoles = auth.roles.length ? auth.roles : [auth.role];
    const normalizedRoles = currentRoles.map(normalizeRole);
    if (normalizedRoles.includes(ROLE_ADMIN)) return true;
    if (Array.isArray(requiredRole)) {
      return requiredRole.some((role) => normalizedRoles.includes(normalizeRole(role)));
    }
    return normalizedRoles.includes(normalizeRole(requiredRole));
  }

  function hasWorkspace(workspace: string | string[]): boolean {
    if (!auth.isAuthed) return false;
    if (Array.isArray(workspace)) {
      return workspace.some((item) => auth.workspaces.includes(item));
    }
    return auth.workspaces.includes(workspace);
  }

  function hasCapability(capability: string | string[]): boolean {
    if (!auth.isAuthed) return false;
    if (Array.isArray(capability)) {
      return capability.some((item) => auth.capabilities.includes(item));
    }
    return auth.capabilities.includes(capability);
  }

  return { hasRole, hasWorkspace, hasCapability };
}
