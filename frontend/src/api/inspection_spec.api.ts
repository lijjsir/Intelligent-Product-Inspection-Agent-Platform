import { http, type ApiRequestConfig } from "./http";
import type { InspectionSpec, InspectionSpecPayload } from "@/types/governance.types";

export const inspectionSpecApi = {
  list(config?: ApiRequestConfig) {
    return http.get<InspectionSpec[]>("/v1/inspection-specs", config);
  },
  get(id: string) {
    return http.get<InspectionSpec>(`/v1/inspection-specs/${id}`);
  },
  create(payload: InspectionSpecPayload) {
    return http.post<InspectionSpec>("/v1/inspection-specs", payload);
  },
  update(id: string, payload: Partial<InspectionSpecPayload>) {
    return http.patch<InspectionSpec>(`/v1/inspection-specs/${id}`, payload);
  },
  remove(id: string) {
    return http.delete<boolean>(`/v1/inspection-specs/${id}`);
  },
};
