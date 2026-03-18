import { http } from "./http";
import type { LoginPayload, RegisterPayload, AuthSession } from "@/types/auth.types";

export const authApi = {
  login(payload: LoginPayload) {
    return http.post<AuthSession>(
      "/v1/auth/token",
      {
        username: payload.username,
        password: payload.password,
      },
      {
        headers: {
          "X-Org-Id": payload.org_id,
        },
      },
    );
  },

  register(payload: RegisterPayload) {
    return http.post<AuthSession>("/v1/auth/register", payload);
  },
};
