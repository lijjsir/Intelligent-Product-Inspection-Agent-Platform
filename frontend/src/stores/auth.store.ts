import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { authApi } from "@/api/auth.api";
import { useUserStore } from "@/stores/user.store";
import type { LoginPayload, RegisterPayload, AuthSession } from "@/types/auth.types";
import {
  ROLE_ADMIN,
  ROLE_AGENT_OPERATOR,
  ROLE_ANALYST,
  ROLE_USER,
  WORKSPACE_APP,
  WORKSPACE_GOVERNANCE,
  WORKSPACE_OPS,
  normalizeRole,
} from "@/constants/roles";
import {
  CAPABILITIES_KEY,
  DEFAULT_WORKSPACE_KEY,
  ORG_ID_KEY,
  PLAN_TIER_KEY,
  ROLE_KEY,
  ROLES_KEY,
  TOKEN_KEY,
  USER_ID_KEY,
  USERNAME_KEY,
  WORKSPACES_KEY,
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
  const workspaces = ref<string[]>(readStoredArray(WORKSPACES_KEY));
  const defaultWorkspace = ref(readStoredValue(DEFAULT_WORKSPACE_KEY) || WORKSPACE_APP);

  if (!roles.value.length && role.value) {
    roles.value = [role.value];
  }
  const normalizedRoles = roles.value.map(normalizeRole);
  if (!workspaces.value.length) {
    if (normalizedRoles.includes(ROLE_ADMIN)) {
      workspaces.value = [WORKSPACE_APP, WORKSPACE_OPS, WORKSPACE_GOVERNANCE];
    } else if (normalizedRoles.includes(ROLE_ANALYST)) {
      workspaces.value = [WORKSPACE_APP, WORKSPACE_GOVERNANCE];
    } else if (normalizedRoles.includes(ROLE_AGENT_OPERATOR)) {
      workspaces.value = [WORKSPACE_OPS];
    } else if (role.value) {
      workspaces.value = [WORKSPACE_APP];
    }
  }

  const isAuthed = computed(() => Boolean(token.value));
  const primaryRole = computed(() => role.value || roles.value[0] || "");

  function normalizeRoles(session: AuthSession): string[] {
    const normalized = Array.from(new Set([session.role, ...(session.roles || [])].filter(Boolean)));
    return normalized.length ? normalized : [session.role];
  }

  function setSession(session: AuthSession) {
    const userStore = useUserStore();
    token.value = session.access_token;
    orgId.value = session.org_id;
    role.value = session.role;
    userId.value = session.user_id;
    username.value = session.username;
    roles.value = normalizeRoles(session);
    planTier.value = session.plan_tier || "basic";
    capabilities.value = [...(session.capabilities || [])];
    workspaces.value = [...(session.workspaces || [WORKSPACE_APP])];
    defaultWorkspace.value = session.default_workspace || workspaces.value[0] || WORKSPACE_APP;

    setStoredValue(TOKEN_KEY, token.value);
    setStoredValue(ORG_ID_KEY, orgId.value);
    setStoredValue(ROLE_KEY, role.value);
    setStoredValue(USER_ID_KEY, userId.value);
    setStoredValue(USERNAME_KEY, username.value);
    setStoredArray(ROLES_KEY, roles.value);
    setStoredValue(PLAN_TIER_KEY, planTier.value);
    setStoredArray(CAPABILITIES_KEY, capabilities.value);
    setStoredArray(WORKSPACES_KEY, workspaces.value);
    setStoredValue(DEFAULT_WORKSPACE_KEY, defaultWorkspace.value);
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
      await userStore.fetchCurrentUser();
    } catch (error) {
      console.warn("Failed to refresh current user profile after auth session setup", error);
    }
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
    const userStore = useUserStore();
    token.value = "";
    orgId.value = "";
    role.value = "";
    userId.value = "";
    username.value = "";
    roles.value = [];
    planTier.value = "basic";
    capabilities.value = [];
    workspaces.value = [];
    defaultWorkspace.value = WORKSPACE_APP;
    clearStoredAuthSession();
    userStore.$reset();
  }

  function hasWorkspace(workspace: string) {
    return workspaces.value.includes(workspace);
  }

  function hasCapability(capability: string) {
    return capabilities.value.includes(capability);
  }

  function resolveDefaultRoute() {
    if (normalizeRole(primaryRole.value) === ROLE_USER) {
      return "/app/chat";
    }
    return "/app/dashboard";
  }

  return {
    token,
    orgId,
    role,
    roles,
    planTier,
    capabilities,
    workspaces,
    defaultWorkspace,
    userId,
    username,
    isAuthed,
    primaryRole,
    login,
    register,
    logout,
    hasWorkspace,
    hasCapability,
    resolveDefaultRoute,
  };
});
