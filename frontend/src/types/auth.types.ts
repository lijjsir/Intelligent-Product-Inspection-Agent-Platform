export interface LoginPayload {
  org_id: string;
  username: string;
  password: string;
}

export interface RegisterPayload {
  create_org: boolean;
  org_name: string;
  org_slug: string;
  username: string;
  email: string;
  password: string;
  role: string;
}

export interface AuthSession {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  username: string;
  org_id: string;
  role: string;
  roles: string[];
  plan_tier: string;
  capabilities: string[];
  workspaces: string[];
  default_workspace: string;
}
