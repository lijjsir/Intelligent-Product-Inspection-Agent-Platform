import { http } from "./http";
import type { InfrastructureStatus } from "@/types/governance.types";

export const infrastructureApi = {
  getStatus() {
    return http.get<InfrastructureStatus>("/v1/infrastructure/status");
  },
  checkAll() {
    return http.post<InfrastructureStatus>("/v1/infrastructure/check-all");
  },
};
