import { http } from "./http";
import type { OverviewStats } from "@/types/analytics.types";
import type { ResponseEnvelope } from "@/types/common.types";

export const analyticsApi = {
  getOverview() {
    return http.get<OverviewStats>("/v1/analytics/overview");
  }
};
