import type { PageParams } from "./common.types";

export interface User {
  id: string;
  org_id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface UserCreate {
  username: string;
  email: string;
  password: string;
  role?: string;
}

export interface UserRoleUpdate {
  role: string;
}

export interface UserStatusUpdate {
  is_active: boolean;
}

export interface UserPasswordReset {
  password: string;
}

export interface UserListQuery extends Partial<PageParams> {
  keyword?: string;
  role?: string;
  is_active?: boolean;
}

export interface UserProfileUpdate {
  username?: string;
  email?: string;
  current_password?: string;
  new_password?: string;
}
