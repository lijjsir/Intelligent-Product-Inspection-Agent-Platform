import { http } from "./http";
import type { User, UserCreate, UserRoleUpdate, UserStatusUpdate } from "@/types/user.types";
import type { PagedResponse, PageParams } from "@/types/common.types";

export const userApi = {
  list(query: PageParams) {
    return http.get<PagedResponse<User>>("/v1/users", { params: query });
  },
  create(payload: UserCreate) {
    return http.post<User>("/v1/users", payload);
  },
  updateRole(id: string, payload: UserRoleUpdate) {
    return http.patch<User>(`/v1/users/${id}/role`, payload);
  },
  updateStatus(id: string, payload: UserStatusUpdate) {
    return http.patch<User>(`/v1/users/${id}/status`, payload);
  }
};
