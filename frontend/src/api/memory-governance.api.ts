import { http } from "./http";
import type {
  MemoryEvaluationPayload,
  MemoryEvaluationResult,
  MemoryEventItem,
  MemoryPolicy,
  MemoryPolicyUpsertPayload,
  MemoryPropagationGraph,
  MemoryRollbackPayload,
  MemoryRollbackResult,
  MemorySearchQueryPayload,
  MemorySearchResult,
} from "@/types/governance.types";

export const memoryGovernanceApi = {
  search(payload: MemorySearchQueryPayload) {
    return http.post<MemorySearchResult>("/v1/memory/search", payload);
  },
  listEvents(params: { memory_id?: string; event_type?: string; trace_id?: string; limit?: number }) {
    return http.get<MemoryEventItem[]>("/v1/memory/events", { params });
  },
  buildPropagationGraph(payload: { org_id: string; workspace: "governance"; root_memory_id: string; trace_id?: string; max_depth?: number }) {
    return http.post<MemoryPropagationGraph>("/v1/memory/contamination/graph", payload);
  },
  executeRollback(payload: MemoryRollbackPayload) {
    return http.post<MemoryRollbackResult>("/v1/memory/rollback", payload);
  },
  evaluateRecovery(payload: MemoryEvaluationPayload) {
    return http.post<MemoryEvaluationResult>("/v1/memory/evaluation/replay", payload);
  },
  listPolicies(params?: { workspace?: string }) {
    return http.get<MemoryPolicy[]>("/v1/memory/policies", { params });
  },
  upsertPolicy(policyKey: string, payload: MemoryPolicyUpsertPayload) {
    return http.put<MemoryPolicy>(`/v1/memory/policies/${policyKey}`, payload);
  },
};
