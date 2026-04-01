import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { authApi } from "@/api/auth.api";
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

const TOKEN_KEY = "piap_token";
const ORG_ID_KEY = "piap_org_id";
const ROLE_KEY = "piap_role";
const USER_ID_KEY = "piap_user_id";
const ROLES_KEY = "piap_roles";
const PLAN_TIER_KEY = "piap_plan_tier";
const CAPABILITIES_KEY = "piap_capabilities";
const WORKSPACES_KEY = "piap_workspaces";
const DEFAULT_WORKSPACE_KEY = "piap_default_workspace";

function readArray(key: string): string[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

export const useAuthStore = defineStore("auth", () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || "");
  const orgId = ref(localStorage.getItem(ORG_ID_KEY) || "");
  const role = ref(localStorage.getItem(ROLE_KEY) || "");
  const userId = ref(localStorage.getItem(USER_ID_KEY) || "");
  const roles = ref<string[]>(readArray(ROLES_KEY));
  const planTier = ref(localStorage.getItem(PLAN_TIER_KEY) || "basic");
  const capabilities = ref<string[]>(readArray(CAPABILITIES_KEY));
  const workspaces = ref<string[]>(readArray(WORKSPACES_KEY));
  const defaultWorkspace = ref(localStorage.getItem(DEFAULT_WORKSPACE_KEY) || WORKSPACE_APP);

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
    token.value = session.access_token;
    orgId.value = session.org_id;
    role.value = session.role;
    userId.value = session.user_id;
    roles.value = normalizeRoles(session);
    planTier.value = session.plan_tier || "basic";
    capabilities.value = [...(session.capabilities || [])];
    workspaces.value = [...(session.workspaces || [WORKSPACE_APP])];
    defaultWorkspace.value = session.default_workspace || workspaces.value[0] || WORKSPACE_APP;

    localStorage.setItem(TOKEN_KEY, token.value);
    localStorage.setItem(ORG_ID_KEY, orgId.value);
    localStorage.setItem(ROLE_KEY, role.value);
    localStorage.setItem(USER_ID_KEY, userId.value);
    localStorage.setItem(ROLES_KEY, JSON.stringify(roles.value));
    localStorage.setItem(PLAN_TIER_KEY, planTier.value);
    localStorage.setItem(CAPABILITIES_KEY, JSON.stringify(capabilities.value));
    localStorage.setItem(WORKSPACES_KEY, JSON.stringify(workspaces.value));
    localStorage.setItem(DEFAULT_WORKSPACE_KEY, defaultWorkspace.value);
  }

  async function login(payload: LoginPayload) {
    const { data } = await authApi.login(payload);
    setSession(data.data);
    return data.data;
  }

  async function register(payload: RegisterPayload) {
    const { data } = await authApi.register(payload);
    setSession(data.data);
    return data.data;
  }

  function logout() {
    token.value = "";
    orgId.value = "";
    role.value = "";
    userId.value = "";
    roles.value = [];
    planTier.value = "basic";
    capabilities.value = [];
    workspaces.value = [];
    defaultWorkspace.value = WORKSPACE_APP;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ORG_ID_KEY);
    localStorage.removeItem(ROLE_KEY);
    localStorage.removeItem(USER_ID_KEY);
    localStorage.removeItem(ROLES_KEY);
    localStorage.removeItem(PLAN_TIER_KEY);
    localStorage.removeItem(CAPABILITIES_KEY);
    localStorage.removeItem(WORKSPACES_KEY);
    localStorage.removeItem(DEFAULT_WORKSPACE_KEY);
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
