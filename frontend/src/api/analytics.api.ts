import { http } from "./http";
import type { ModelDrilldown, OverviewStats, ProductLineDrilldown } from "@/types/analytics.types";

export const analyticsApi = {
  getOverview(params?: { start_date?: string; end_date?: string }) {
    return http.get<OverviewStats>("/v1/analytics/overview", { params });
  },
  getProductLineDrilldown(productLine: string, params?: { start_date?: string; end_date?: string }) {
    return http.get<ProductLineDrilldown>(`/v1/analytics/product-lines/${encodeURIComponent(productLine)}`, { params });
  },
  getModelDrilldown(modelKey: string, params?: { start_date?: string; end_date?: string }) {
    return http.get<ModelDrilldown>(`/v1/analytics/models/${encodeURIComponent(modelKey)}`, { params });
  }
};
