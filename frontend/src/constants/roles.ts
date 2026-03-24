export const ROLE_SUPER_ADMIN = "super_admin";
export const ROLE_ORG_ADMIN = "org_admin";
export const ROLE_INSPECTOR = "inspector";
export const ROLE_VIEWER = "viewer";
export const ROLE_ANALYST = "analyst";
export const ROLE_PLATFORM_ADMIN = "platform_admin";
export const ROLE_AI_QUALITY = "ai_quality";
export const ROLE_AGENT_OPERATOR = "agent_operator";

export const ALL_ROLES = [
  ROLE_SUPER_ADMIN,
  ROLE_ORG_ADMIN,
  ROLE_INSPECTOR,
  ROLE_VIEWER,
  ROLE_ANALYST,
  ROLE_PLATFORM_ADMIN,
  ROLE_AI_QUALITY,
  ROLE_AGENT_OPERATOR,
] as const;

export const WORKSPACE_APP = "app";
export const WORKSPACE_OPS = "ops";
export const WORKSPACE_GOVERNANCE = "governance";
