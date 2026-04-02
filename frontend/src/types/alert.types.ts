import type { PageParams } from "./common.types";

export type AlertStatus = "open" | "acknowledged" | "suppressed" | "resolved";
export type AlertAction = "acknowledge" | "suppress" | "resolve";
export type AlertSeverity = "info" | "warning" | "error" | "critical";

export interface AlertListQuery extends PageParams {
  status?: string;
  severity?: string;
}

export interface AlertHandlePayload {
  action: AlertAction;
  action_note?: string;
}

export interface AlertEvent {
  id: string;
  org_id: string;
  stability_id?: string;
  alert_type: string;
  severity: AlertSeverity | string;
  title: string;
  detail?: Record<string, any>;
  status: AlertStatus | string;
  channels?: Record<string, any>;
  dispatched_at?: string;
  ack_by?: string;
  ack_at?: string;
  resolved_by?: string;
  resolved_at?: string;
  suppressed_by?: string;
  suppressed_at?: string;
  action_note?: string;
  created_at?: string;
}
