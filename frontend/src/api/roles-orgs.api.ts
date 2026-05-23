import { http } from "./http";
import type {
  Organization,
  OrganizationCreatePayload,
  OrganizationUpdatePayload,
  OrganizationUserAssignmentPayload,
  OrganizationUsersResponse,
  RoleItem,
  RolesPermissionMatrix,
} from "@/types/governance.types";

export const rolesOrgsApi = {
  listRoles() {
    return http.get<RoleItem[]>("/v1/roles");
  },
  getPermissionsMatrix() {
    return http.get<RolesPermissionMatrix>("/v1/roles/permissions");
  },
  listOrganizations() {
    return http.get<Organization[]>("/v1/organizations");
  },
  createOrganization(payload: OrganizationCreatePayload) {
    return http.post<Organization>("/v1/organizations", payload);
  },
  updateOrganization(id: string, payload: OrganizationUpdatePayload) {
    return http.patch<Organization>(`/v1/organizations/${id}`, payload);
  },
  deleteOrganization(id: string) {
    return http.delete<{ success: boolean }>(`/v1/organizations/${id}`);
  },
  getOrganizationUsers(orgId: string) {
    return http.get<OrganizationUsersResponse>(`/v1/organizations/${orgId}/users`);
  },
  assignUsersToOrganization(orgId: string, payload: OrganizationUserAssignmentPayload) {
    return http.post<{ affected: number }>(`/v1/organizations/${orgId}/users`, payload);
  },
};
