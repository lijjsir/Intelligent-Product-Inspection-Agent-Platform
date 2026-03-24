import { http } from "./http";
import type { BillingQuery, BillingSummary } from "@/types/governance.types";

export const billingApi = {
  getSummary(query: BillingQuery) {
    return http.get<BillingSummary>("/v1/billing/summary", { params: query });
  },
};

