import { http } from "./http";
import type {
  ExportJob,
  ExportJobCreatePayload,
  ExportJobQuery,
} from "@/types/governance.types";
import type { PagedResponse } from "@/types/common.types";

export const exportApi = {
  create(payload: ExportJobCreatePayload) {
    return http.post<ExportJob>("/v1/exports", payload);
  },
  list(query: ExportJobQuery) {
    return http.get<PagedResponse<ExportJob>>("/v1/exports", { params: query });
  },
  detail(id: string) {
    return http.get<ExportJob>(`/v1/exports/${id}`);
  },
  remove(id: string) {
    return http.delete(`/v1/exports/${id}`);
  },
};
