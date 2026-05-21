import type { PageParams } from "./common.types";

export type AlertSeverity = "info" | "warning" | "error" | "critical";

export interface AlertRule {
  id: string;
  org_id: string;
  name: string;
  description?: string;
  alert_type: string;
  severity: AlertSeverity | string;
  enabled: boolean;
  condition_config?: Record<string, any>;
  notification_channels?: Record<string, any>;
  cooldown_seconds: number;
  created_at?: string;
  updated_at?: string;
}

export interface AlertRuleCreate {
  name: string;
  description?: string;
  alert_type: string;
  severity?: string;
  enabled?: boolean;
  condition_config?: Record<string, any>;
  notification_channels?: Record<string, any>;
  cooldown_seconds?: number;
}

export interface AlertRuleUpdate {
  name?: string;
  description?: string;
  alert_type?: string;
  severity?: string;
  enabled?: boolean;
  condition_config?: Record<string, any>;
  notification_channels?: Record<string, any>;
  cooldown_seconds?: number;
}

export interface AlertRuleListQuery extends PageParams {
  severity?: string;
  enabled?: boolean;
}
