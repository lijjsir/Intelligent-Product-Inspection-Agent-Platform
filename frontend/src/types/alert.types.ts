import type { PageParams } from "./common.types";

export interface AlertListQuery extends PageParams {
  status?: string;
  severity?: string;
}

export interface AlertEvent {
  id: string;
  org_id: string;
  stability_id?: string;
  alert_type: string;
  severity: "info" | "warning" | "error" | "critical" | string;
  title: string;
  detail?: Record<string, any>;
  status: "open" | "resolved" | string;
  channels?: Record<string, any>;
  dispatched_at?: string;
  ack_by?: string;
  ack_at?: string;
  resolved_by?: string;
  resolved_at?: string;
  created_at?: string;
}
