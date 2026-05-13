import { http } from "./http";
import type { BillingQuery, BillingSummary, CurrentUserTokenUsage } from "@/types/governance.types";

export const billingApi = {
  getSummary(query: BillingQuery) {
    return http.get<BillingSummary>("/v1/billing/summary", { params: query });
  },
  getMyUsage() {
    return http.get<CurrentUserTokenUsage>("/v1/billing/me");
  },
};

