export interface LoginPayload {
  org_id: string;
  username: string;
  password: string;
}

export interface RegisterPayload {
  org_name: string;
  org_slug: string;
  username: string;
  email: string;
  password: string;
}

export interface AuthSession {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  org_id: string;
  role: string;
}
