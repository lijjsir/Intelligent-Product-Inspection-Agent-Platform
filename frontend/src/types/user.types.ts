import type { PageParams } from "./common.types";

export interface User {
  id: string;
  org_id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
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
