import { http } from "./http";
import type { InspectionStandardLibraryItem, InspectionStandardPayload } from "@/types/governance.types";

export const inspectionStandardApi = {
  list() {
    return http.get<InspectionStandardLibraryItem[]>("/v1/inspection-standards");
  },
  get(id: string) {
    return http.get<InspectionStandardLibraryItem>(`/v1/inspection-standards/${id}`);
  },
  create(payload: InspectionStandardPayload) {
    return http.post<InspectionStandardLibraryItem>("/v1/inspection-standards", payload);
  },
  update(id: string, payload: Partial<InspectionStandardPayload>) {
    return http.patch<InspectionStandardLibraryItem>(`/v1/inspection-standards/${id}`, payload);
  },
  remove(id: string) {
    return http.delete<{ success: boolean }>(`/v1/inspection-standards/${id}`);
  },
};
