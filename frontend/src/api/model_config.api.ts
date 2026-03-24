import { http } from "./http";
import type { ModelConfig, ModelConfigPayload } from "@/types/governance.types";

export const modelConfigApi = {
  list() {
    return http.get<ModelConfig[]>("/v1/model-configs");
  },
  create(payload: ModelConfigPayload) {
    return http.post<ModelConfig>("/v1/model-configs", payload);
  },
  update(id: string, payload: Partial<ModelConfigPayload>) {
    return http.patch<ModelConfig>(`/v1/model-configs/${id}`, payload);
  },
  remove(id: string) {
    return http.delete<boolean>(`/v1/model-configs/${id}`);
  },
};

