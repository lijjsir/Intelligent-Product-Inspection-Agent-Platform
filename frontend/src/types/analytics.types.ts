export interface TrendPoint {
  bucket: string;
  value: number;
}

export interface RiskTrendPoint {
  bucket: string;
  low: number;
  medium: number;
  high: number;
  critical: number;
}

export interface NamedValue {
  name: string;
  value: number;
}

export interface ModelAnalyticsMetric {
  model_key: string;
  result_count: number;
  pass_rate: number;
  hallucination_rate: number;
  avg_tokens: number;
  total_cost: number;
}

export interface ProductLineSeries {
  name: string;
  total_tasks: number;
  pass_rate: number;
  points: TrendPoint[];
}

export interface ProductLineRecentTask {
  task_id: string;
  status: string;
  spec_id: string;
  created_at: string;
}

export interface ProductLineDrilldown {
  product_line: string;
  total_tasks: number;
  total_results: number;
  pass_rate: number;
  hallucination_rate: number;
  avg_latency_ms: number;
  total_cost: number;
  task_trend: TrendPoint[];
  verdict_distribution: NamedValue[];
  recent_tasks: ProductLineRecentTask[];
}

export interface ModelRecentResult {
  result_id: string;
  task_id: string;
  product_line: string;
  verdict: string;
  overall_score: number;
  created_at: string;
}

export interface ModelDrilldown {
  model_key: string;
  result_count: number;
  pass_rate: number;
  hallucination_rate: number;
  avg_tokens: number;
  total_cost: number;
  avg_latency_ms: number;
  product_line_distribution: NamedValue[];
  recent_results: ModelRecentResult[];
}

export interface OverviewStats {
  total_tasks: number;
  total_alerts: number;
  total_results: number;
  total_cost: number;
  pass_rate: number;
  hallucination_rate: number;
  risk_yellow_rate: number;
  avg_risk_score: number;
  avg_latency_ms: number;
  task_trend: TrendPoint[];
  pass_rate_trend: TrendPoint[];
  hallucination_trend: TrendPoint[];
  risk_distribution_trend: RiskTrendPoint[];
  risk_distribution: NamedValue[];
  alert_distribution: NamedValue[];
  model_metrics: ModelAnalyticsMetric[];
  product_line_series: ProductLineSeries[];
}
