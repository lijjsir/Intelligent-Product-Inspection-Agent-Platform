import { ref } from "vue";
import { useAuthStore } from "@/stores/auth.store";

export function usePermission() {
  const auth = useAuthStore();

  function hasRole(requiredRole: string | string[]): boolean {
    if (!auth.isAuthed) return false;
    const currentRole = auth.role;
    if (currentRole === "super_admin" || currentRole === "org_admin") return true;
    if (Array.isArray(requiredRole)) {
      return requiredRole.includes(currentRole);
    }
    return currentRole === requiredRole;
  }

  return { hasRole };
}
