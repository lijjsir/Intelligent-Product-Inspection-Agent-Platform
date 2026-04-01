export const ROLE_ADMIN = "admin";
export const ROLE_USER = "user";
export const ROLE_INSPECTOR = "inspector";
export const ROLE_ANALYST = "analyst";
export const ROLE_AGENT_OPERATOR = "agent_operator";
export const ROLE_API_SERVICE = "api_service";

export const ALL_ROLES = [
  ROLE_ADMIN,
  ROLE_USER,
  ROLE_INSPECTOR,
  ROLE_ANALYST,
  ROLE_AGENT_OPERATOR,
  ROLE_API_SERVICE,
] as const;

export const LEGACY_ROLE_MAP: Record<string, string> = {
  super_admin: ROLE_ADMIN,
  org_admin: ROLE_ADMIN,
  platform_admin: ROLE_ADMIN,
  auditor: ROLE_ADMIN,
  viewer: ROLE_INSPECTOR,
  ai_quality: ROLE_ANALYST,
};

export const WORKSPACE_APP = "app";
export const WORKSPACE_OPS = "ops";
export const WORKSPACE_GOVERNANCE = "governance";

export function normalizeRole(role: string): string {
  return LEGACY_ROLE_MAP[role] || role;
}
