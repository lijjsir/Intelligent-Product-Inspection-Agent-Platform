import { http } from "./http";
import type { AlertEvent, AlertListQuery } from "@/types/alert.types";
import type { PagedResponse } from "@/types/common.types";

export const alertApi = {
  list(query: AlertListQuery) {
    return http.get<PagedResponse<AlertEvent>>("/v1/alerts", { params: query });
  },
  get(id: string) {
    return http.get<AlertEvent>(`/v1/alerts/${id}`);
  },
  resolve(id: string) {
    return http.put<boolean>(`/v1/alerts/${id}/resolve`);
  }
};
