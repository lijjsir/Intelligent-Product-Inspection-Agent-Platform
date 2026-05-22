export type GpuNodeStatus = "online" | "offline" | "error" | "disabled";

export interface GpuComputeNode {
  id: string;
  org_id: string;
  created_by?: string | null;
  name: string;
  host: string;
  ssh_port: number;
  ssh_username: string;
  total_gpu_count: number;
  available_gpu_count: number;
  gpu_bitmap: string;
  cpu_usage?: number | null;
  memory_usage?: number | null;
  gpu_usage?: number | null;
  status: GpuNodeStatus;
  last_heartbeat?: string | null;
  load_score?: number | null;
  metadata_json?: Record<string, unknown> | null;
  has_ssh_password: boolean;
  has_ssh_private_key: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface GpuNodeCreatePayload {
  name: string;
  host: string;
  ssh_port?: number;
  ssh_username: string;
  ssh_password?: string | null;
  ssh_private_key?: string | null;
  total_gpu_count?: number;
  metadata_json?: Record<string, unknown> | null;
}

export interface GpuNodeUpdatePayload {
  name?: string;
  host?: string;
  ssh_port?: number;
  ssh_username?: string;
  ssh_password?: string | null;
  ssh_private_key?: string | null;
  total_gpu_count?: number;
  metadata_json?: Record<string, unknown> | null;
}

export interface GpuNodeHeartbeatPayload {
  cpu_usage?: number | null;
  memory_usage?: number | null;
  gpu_usage?: number | null;
  gpu_bitmap?: string | null;
}

export interface GpuNodeConnectionTestResult {
  success: boolean;
  message: string;
}

export interface GpuNodeMetricRefreshResult {
  node: GpuComputeNode;
  metrics: Record<string, unknown>;
}
