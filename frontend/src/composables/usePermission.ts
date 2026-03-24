import { ref } from "vue";
import { useAuthStore } from "@/stores/auth.store";
import { ROLE_SUPER_ADMIN } from "@/constants/roles";

export function usePermission() {
  const auth = useAuthStore();

  function hasRole(requiredRole: string | string[]): boolean {
    if (!auth.isAuthed) return false;
    const currentRole = auth.role;
    if (currentRole === ROLE_SUPER_ADMIN) return true;
    if (Array.isArray(requiredRole)) {
      return requiredRole.includes(currentRole);
    }
    return currentRole === requiredRole;
  }

  return { hasRole };
}
