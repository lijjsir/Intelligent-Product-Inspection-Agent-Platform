export const TOKEN_KEY = "piap_token";
export const ORG_ID_KEY = "piap_org_id";
export const ROLE_KEY = "piap_role";
export const USER_ID_KEY = "piap_user_id";
export const USERNAME_KEY = "piap_username";
export const ROLES_KEY = "piap_roles";
export const PLAN_TIER_KEY = "piap_plan_tier";
export const CAPABILITIES_KEY = "piap_capabilities";
export const WORKSPACES_KEY = "piap_workspaces";
export const DEFAULT_WORKSPACE_KEY = "piap_default_workspace";

const STORAGE_KEYS = [
  TOKEN_KEY,
  ORG_ID_KEY,
  ROLE_KEY,
  USER_ID_KEY,
  USERNAME_KEY,
  ROLES_KEY,
  PLAN_TIER_KEY,
  CAPABILITIES_KEY,
  WORKSPACES_KEY,
  DEFAULT_WORKSPACE_KEY,
];

function getSessionAuthStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage;
}

function getLegacyAuthStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

export function readStoredValue(key: string): string {
  const sessionStorageRef = getSessionAuthStorage();
  const sessionValue = sessionStorageRef?.getItem(key);
  if (sessionValue) {
    return sessionValue;
  }

  const legacyStorageRef = getLegacyAuthStorage();
  const legacyValue = legacyStorageRef?.getItem(key);
  if (!legacyValue) {
    return "";
  }

  sessionStorageRef?.setItem(key, legacyValue);
  legacyStorageRef?.removeItem(key);
  return legacyValue;
}

export function setStoredValue(key: string, value: string) {
  const sessionStorageRef = getSessionAuthStorage();
  if (value) {
    sessionStorageRef?.setItem(key, value);
  } else {
    sessionStorageRef?.removeItem(key);
  }
  getLegacyAuthStorage()?.removeItem(key);
}

export function setStoredArray(key: string, value: string[]) {
  setStoredValue(key, JSON.stringify(value));
}

export function readStoredArray(key: string): string[] {
  try {
    const raw = readStoredValue(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

export function clearStoredAuthSession() {
  const sessionStorageRef = getSessionAuthStorage();
  const legacyStorageRef = getLegacyAuthStorage();
  for (const key of STORAGE_KEYS) {
    sessionStorageRef?.removeItem(key);
    legacyStorageRef?.removeItem(key);
  }
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem("chat_current_session_id");
  }
}
