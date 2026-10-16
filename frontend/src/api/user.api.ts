import { http } from "./http";
import type { UserPermissions, UserPermissionUpdate } from "@/types/permission.types";
import type {
  User,
  UserCreate,
  UserListQuery,
  UserPasswordReset,
  UserProfileUpdate,
  UserRoleUpdate,
  UserStatusUpdate,
  UserPermissionDirectory,
} from "@/types/user.types";
import type { PagedResponse, PageParams } from "@/types/common.types";

export const userApi = {
  list(query: PageParams | UserListQuery) {
    return http.get<PagedResponse<User>>("/v1/users", { params: query });
  },
  permissionDirectory(query: UserListQuery) {
    return http.get<UserPermissionDirectory>("/v1/users/meta/permission-directory", { params: query });
  },
  create(payload: UserCreate) {
    return http.post<User>("/v1/users", payload);
  },
  getMe() {
    return http.get<User>("/v1/users/me");
  },
  getPermissions(id: string) {
    return http.get<UserPermissions>(`/v1/users/${id}/permissions`);
  },
  updatePermissions(id: string, payload: UserPermissionUpdate) {
    return http.put<UserPermissions>(`/v1/users/${id}/permissions`, payload);
  },
  updateMe(payload: UserProfileUpdate) {
    return http.patch<User>("/v1/users/me", payload);
  },
  getAssignableRoles() {
    return http.get<string[]>("/v1/users/meta/assignable-roles");
  },
  updateRole(id: string, payload: UserRoleUpdate) {
    return http.patch<User>(`/v1/users/${id}/role`, payload);
  },
  updateStatus(id: string, payload: UserStatusUpdate) {
    return http.patch<User>(`/v1/users/${id}/status`, payload);
  },
  resetPassword(id: string, payload: UserPasswordReset) {
    return http.patch<User>(`/v1/users/${id}/password`, payload);
  },
};
