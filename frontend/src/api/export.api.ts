import instance, { http } from "./http";
import type { ExportJob, ExportJobCreatePayload, ExportJobQuery } from "@/types/governance.types";
import type { PagedResponse } from "@/types/common.types";

export const exportApi = {
  create(payload: ExportJobCreatePayload) {
    return http.post<ExportJob>("/v1/exports", payload);
  },
  list(query: ExportJobQuery) {
    return http.get<PagedResponse<ExportJob>>("/v1/exports", { params: query });
  },
  detail(id: string, timeout = 60000) {
    return http.get<ExportJob>(`/v1/exports/${id}`, { timeout });
  },
  remove(id: string) {
    return http.delete(`/v1/exports/${id}`);
  },
  download(id: string) {
    return instance.get<Blob>(`/v1/exports/${id}/download`, { responseType: "blob" });
  },
};
