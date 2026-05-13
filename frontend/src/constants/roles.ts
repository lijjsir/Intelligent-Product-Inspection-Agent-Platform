export const ROLE_ADMIN = "admin";
export const ROLE_APP_DEVELOPER = "app_developer";
export const ROLE_PLATFORM_OPERATOR = "platform_operator";
export const ROLE_ALGORITHM_ENGINEER = "algorithm_engineer";
export const ROLE_USER = "user";
export const ROLE_EXPERT = "expert";

export const ALL_ROLES = [
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_PLATFORM_OPERATOR,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_USER,
  ROLE_EXPERT,
] as const;

export const WORKSPACE_APP = "app";
export const WORKSPACE_OPS = "ops";
export const WORKSPACE_GOVERNANCE = "governance";

export const CAPABILITY_PRIVATE_RAG = "private_rag";
export const CAPABILITY_CUSTOM_PROMPT = "custom_prompt";
export const CAPABILITY_CUSTOM_WORKFLOW = "custom_workflow";
export const CAPABILITY_COT_CONTROL = "cot_control";
export const CAPABILITY_GOVERNANCE = "governance_console";
export const CAPABILITY_ADVANCED_ANALYTICS = "advanced_analytics";
export const CAPABILITY_MODEL_CONTROL = "model_control";
