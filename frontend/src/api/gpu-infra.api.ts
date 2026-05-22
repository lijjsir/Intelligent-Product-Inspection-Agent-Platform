import { http } from "./http";
import type {
  GpuComputeNode,
  GpuNodeConnectionTestResult,
  GpuNodeCreatePayload,
  GpuNodeHeartbeatPayload,
  GpuNodeMetricRefreshResult,
  GpuNodeUpdatePayload,
} from "@/types/gpu-infra.types";

export const gpuInfraApi = {
  list() {
    return http.get<GpuComputeNode[]>("/v1/gpu-nodes");
  },
  get(id: string) {
    return http.get<GpuComputeNode>(`/v1/gpu-nodes/${id}`);
  },
  create(payload: GpuNodeCreatePayload) {
    return http.post<GpuComputeNode>("/v1/gpu-nodes", payload);
  },
  update(id: string, payload: GpuNodeUpdatePayload) {
    return http.patch<GpuComputeNode>(`/v1/gpu-nodes/${id}`, payload);
  },
  remove(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/gpu-nodes/${id}`);
  },
  testConnection(id: string) {
    return http.post<GpuNodeConnectionTestResult>(`/v1/gpu-nodes/${id}/test-connection`);
  },
  heartbeat(id: string, payload: GpuNodeHeartbeatPayload) {
    return http.post<GpuComputeNode>(`/v1/gpu-nodes/${id}/heartbeat`, payload);
  },
  refreshMetrics(id: string) {
    return http.post<GpuNodeMetricRefreshResult>(`/v1/gpu-nodes/${id}/refresh-metrics`);
  },
  enable(id: string) {
    return http.post<GpuComputeNode>(`/v1/gpu-nodes/${id}/enable`);
  },
  disable(id: string) {
    return http.post<GpuComputeNode>(`/v1/gpu-nodes/${id}/disable`);
  },
};

