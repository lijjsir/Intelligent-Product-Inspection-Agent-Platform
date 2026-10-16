export type PermissionEffect = "grant" | "deny";

export interface PermissionGroup {
  key: string;
  label: string;
}

export interface PermissionAction {
  key: string;
  group: string;
  name: string;
  action: string;
  description?: string;
  role_presentation?: Record<string, { name?: string; action?: string; description?: string }>;
  requires?: string[];
}

export interface UserPermissions {
  user_id: string;
  username: string;
  role: string;
  role_default: string[];
  role_version: number;
  overrides: Record<string, PermissionEffect>;
  effective: string[];
  version: number;
  is_active: boolean;
}

export interface UserPermissionUpdate {
  role: string;
  expected_role: string;
  overrides: Record<string, PermissionEffect>;
  version: number;
}
