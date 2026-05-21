import { useAuthStore } from "@/stores/auth.store";

export function usePermission() {
  const auth = useAuthStore();

  function hasRole(requiredRole: string | string[]): boolean {
    if (!auth.isAuthed) return false;
    const currentRoles = auth.roles.length ? auth.roles : [auth.role];
    if (Array.isArray(requiredRole)) {
      return requiredRole.some((role) => currentRoles.includes(role));
    }
    return currentRoles.includes(requiredRole);
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
