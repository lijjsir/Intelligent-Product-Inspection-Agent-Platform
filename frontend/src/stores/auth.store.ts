import { defineStore } from "pinia";
import { adminLandingPaths } from "@/utils/admin-workspace";
import { computed, ref } from "vue";
import { authApi } from "@/api/auth.api";
import { userApi } from "@/api/user.api";
import { roleMenuPaths } from "@/utils/role-navigation";
import { permissionsForRoute } from "@/utils/permission-routes";
import { useUserStore } from "@/stores/user.store";
import type { LoginPayload, RegisterPayload, AuthSession } from "@/types/auth.types";
import {
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_PLATFORM_OPERATOR,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_USER,
  ROLE_EXPERT,
} from "@/constants/roles";
import {
  CAPABILITIES_KEY,
  ORG_ID_KEY,
  PLAN_TIER_KEY,
  ROLE_KEY,
  ROLES_KEY,
  TOKEN_KEY,
  USER_ID_KEY,
  USERNAME_KEY,
  clearStoredAuthSession,
  readStoredArray,
  readStoredValue,
  setStoredArray,
  setStoredValue,
} from "@/utils/auth-session";

export const useAuthStore = defineStore("auth", () => {
  const token = ref(readStoredValue(TOKEN_KEY));
  const orgId = ref(readStoredValue(ORG_ID_KEY));
  const role = ref(readStoredValue(ROLE_KEY));
  const userId = ref(readStoredValue(USER_ID_KEY));
  const username = ref(readStoredValue(USERNAME_KEY));
  const roles = ref<string[]>(readStoredArray(ROLES_KEY));
  const planTier = ref(readStoredValue(PLAN_TIER_KEY) || "basic");
  const capabilities = ref<string[]>(readStoredArray(CAPABILITIES_KEY));
  const effectivePermissions = ref<string[] | null>(null);
  let permissionRefresh: Promise<boolean> | null = null;
  let sessionVersion = 0;

  if (!roles.value.length && role.value) {
    roles.value = [role.value];
  }

  const isAuthed = computed(() => Boolean(token.value));
  const primaryRole = computed(() => role.value || roles.value[0] || "");

  function normalizeRoles(session: AuthSession): string[] {
    const normalized = Array.from(new Set([session.role, ...(session.roles || [])].filter(Boolean)));
    return normalized.length ? normalized : [session.role];
  }

  function setSession(session: AuthSession) {
    sessionVersion++;
    permissionRefresh = null;
    const userStore = useUserStore();
    token.value = session.access_token;
    orgId.value = session.org_id;
    role.value = session.role;
    userId.value = session.user_id;
    username.value = session.username;
    roles.value = normalizeRoles(session);
    planTier.value = session.plan_tier || "basic";
    capabilities.value = [...(session.capabilities || [])];
    effectivePermissions.value = null;

    setStoredValue(TOKEN_KEY, token.value);
    setStoredValue(ORG_ID_KEY, orgId.value);
    setStoredValue(ROLE_KEY, role.value);
    setStoredValue(USER_ID_KEY, userId.value);
    setStoredValue(USERNAME_KEY, username.value);
    setStoredArray(ROLES_KEY, roles.value);
    setStoredValue(PLAN_TIER_KEY, planTier.value);
    setStoredArray(CAPABILITIES_KEY, capabilities.value);
    userStore.current = {
      id: session.user_id,
      org_id: session.org_id,
      username: session.username,
      email: userStore.current?.email || "",
      role: session.role,
      is_active: true,
      created_at: userStore.current?.created_at,
      updated_at: userStore.current?.updated_at,
    };
  }

  async function syncCurrentUserProfile() {
    const userStore = useUserStore();
    try {
      const user = await userStore.fetchCurrentUser();
      applyCurrentPermissions(user);
    } catch (error) {
      console.warn("Failed to refresh current user profile after auth session setup", error);
    }
  }

  function applyCurrentPermissions(user: import("@/types/user.types").User) {
    if (user.effective_permissions == null) return;
    effectivePermissions.value = [...user.effective_permissions];
    role.value = user.role;
    roles.value = [user.role];
    setStoredValue(ROLE_KEY, user.role);
    setStoredArray(ROLES_KEY, roles.value);
    if (user.capabilities) {
      capabilities.value = [...user.capabilities];
      setStoredArray(CAPABILITIES_KEY, capabilities.value);
    }
  }

  async function refreshPermissions(): Promise<boolean> {
    if (!isAuthed.value) return false;
    if (permissionRefresh) return permissionRefresh;
    const version = sessionVersion;
    permissionRefresh = (async () => {
      try {
        const { data } = await userApi.getMe();
        if (version !== sessionVersion) return false;
        applyCurrentPermissions(data.data);
        return true;
      } catch {
        if (version === sessionVersion) effectivePermissions.value = [];
        return false;
      } finally { if (version === sessionVersion) permissionRefresh = null; }
    })();
    return permissionRefresh;
  }

  function hasPermission(permission: string | string[]) {
    if (!isAuthed.value || effectivePermissions.value === null) return false;
    const required = Array.isArray(permission) ? permission : [permission];
    return required.some((key) => effectivePermissions.value!.includes(key));
  }

  async function login(payload: LoginPayload) {
    const { data } = await authApi.login(payload);
    setSession(data.data);
    await syncCurrentUserProfile();
    return data.data;
  }

  async function register(payload: RegisterPayload) {
    const { data } = await authApi.register(payload);
    setSession(data.data);
    await syncCurrentUserProfile();
    return data.data;
  }

  function logout() {
    sessionVersion++;
    permissionRefresh = null;
    const userStore = useUserStore();
    token.value = "";
    orgId.value = "";
    role.value = "";
    userId.value = "";
    username.value = "";
    roles.value = [];
    planTier.value = "basic";
    capabilities.value = [];
    effectivePermissions.value = null;
    clearStoredAuthSession();
    userStore.$reset();
  }

  function hasCapability(capability: string) {
    return capabilities.value.includes(capability);
  }

  function resolveDefaultRoute() {
    const r = primaryRole.value;
    if (r === ROLE_ADMIN) {
      if (effectivePermissions.value === null) return "/governance/admin/users";
      return adminLandingPaths().find(path => {
        const keys = permissionsForRoute(path);
        return !keys || hasPermission(keys);
      }) || "/app/profile";
    }
    if (effectivePermissions.value !== null) {
      const preferred = r === ROLE_ADMIN ? "/governance/admin/users"
        : r === ROLE_ALGORITHM_ENGINEER ? "/ops/data/import"
        : r === ROLE_APP_DEVELOPER ? "/ops/agents"
        : r === ROLE_PLATFORM_OPERATOR ? "/ops/dashboard"
        : r === ROLE_EXPERT ? "/app/workbench" : "/app/chat";
      const keys = permissionsForRoute(preferred);
      if (!keys || hasPermission(keys)) return preferred;
      return roleMenuPaths(r).find(path => {
        const routeKeys = permissionsForRoute(path);
        return routeKeys && hasPermission(routeKeys);
      }) || "/app/profile";
    }
    if (r === ROLE_EXPERT) return "/app/workbench";
    if (r === ROLE_USER) {
      return "/app/chat";
    }
    if (r === ROLE_ADMIN) {
      return "/governance/admin/users";
    }
    if (r === ROLE_ALGORITHM_ENGINEER) {
      return "/ops/data/import";
    }
    if (r === ROLE_APP_DEVELOPER) {
      return "/ops/agents";
    }
    if (r === ROLE_PLATFORM_OPERATOR) {
      return "/ops/dashboard";
    }
    return "/app/profile";
  }

  return {
    token,
    orgId,
    role,
    roles,
    planTier,
    capabilities,
    effectivePermissions,
    refreshPermissions,
    hasPermission,
    userId,
    username,
    isAuthed,
    primaryRole,
    login,
    register,
    logout,
    hasCapability,
    resolveDefaultRoute,
  };
});
