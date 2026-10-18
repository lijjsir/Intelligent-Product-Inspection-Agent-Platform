export type MarketObjectType = "product" | "enterprise";
export type MarketKind = "consumer_complaint" | "public_opinion";
export type MarketStatus = "normal" | "insufficient_coverage" | "quantity_growth" | "new_cluster";
export interface MarketRule {
  version: number;
  algorithm: string;
  window_days: number;
  min_current: number;
  min_increase: number;
  growth_factor: number;
}
export interface MarketWindows {
  previous_start: string;
  current_start: string;
  end: string;
  timezone: string;
}
export interface MarketRecordSummary {
  id: string;
  record_type: MarketKind;
  occurred_at: string | null;
  external_record_id: string | null;
  text: string;
}
export interface MarketGroup {
  execution_mode: string;
  as_of: string;
  object_type: MarketObjectType;
  object_id: string;
  object_name: string;
  record_type: MarketKind;
  status: MarketStatus;
  previous_count: number;
  current_count: number;
  growth_percent: number | null;
  signal_id: string | null;
  case_id: string | null;
  source_record_ids: string[];
  rule: MarketRule;
  windows: MarketWindows;
  uncovered_sources: string[];
}
export interface MarketReport {
  date_basis?: "explicit" | "demo_anchor" | "current_day";
  demo_anchor_as_of?: string | null;
  execution_mode: string;
  as_of: string;
  object_type: MarketObjectType;
  windows: MarketWindows;
  rule: MarketRule;
  totals: Record<MarketKind, { previous: number; current: number }>;
  daily: Array<{ day: string } & Record<MarketKind, number>>;
  groups: MarketGroup[];
  pending_objects: MarketRecordSummary[];
  missing_time: MarketRecordSummary[];
  unavailable_sources: MarketRecordSummary[];
  notice: string;
}
export interface MarketSignalDetail {
  id: string;
  name: string;
  snapshot: Omit<MarketGroup, "object_name" | "signal_id" | "uncovered_sources" | "case_id"> & {
    case_id?: string;
    converted_by?: string;
    converted_at?: string;
  };
  is_current: boolean;
  records: MarketRecordSummary[];
}
export interface MarketFocus {
  id: string;
  object_type: MarketObjectType;
  object_id: string;
  object_name: string;
  reason: string;
  available: boolean;
  at: string;
}
export interface MarketCoverage {
  source_id: string;
  source_name: string;
  record_type: MarketKind;
  coverage: { start_at: string; end_at: string; reason: string; actor_id: string } | null;
}
