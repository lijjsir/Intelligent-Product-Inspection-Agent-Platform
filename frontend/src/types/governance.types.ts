export interface ModelConfig {
  id: string;
  org_id: string | null;
  provider: string;
  model_key: string;
  display_name: string;
  endpoint: string;
  model_type: string;
  priority: number;
  rpm_limit: number | null;
  input_price_per_million: number | null;
  output_price_per_million: number | null;
  is_active: boolean;
  health_status: string;
  health_message: string | null;
  has_api_key: boolean;
}

export interface ModelConfigPayload {
  org_id?: string | null;
  provider: string;
  model_key: string;
  display_name: string;
  endpoint: string;
  api_key?: string | null;
  model_type?: string;
  priority?: number;
  rpm_limit?: number | null;
  input_price_per_million?: number | null;
  output_price_per_million?: number | null;
  is_active?: boolean;
}

export interface BillingBucket {
  bucket: string;
  total_tokens: number;
  total_cost: number;
  request_count: number;
}

export interface TokenLedger {
  id: string;
  model_key: string;
  product_line: string | null;
  total_tokens: number;
  cost_amount: number;
  trace_id: string | null;
  created_at: string;
}

export interface BillingSummary {
  granularity: string;
  total_tokens: number;
  total_cost: number;
  buckets: BillingBucket[];
  ledger_items: TokenLedger[];
}

export interface BillingQuery {
  start_date?: string;
  end_date?: string;
  granularity?: "day" | "week" | "month";
  model_key?: string;
  product_line?: string;
}

export interface ResultFeedback {
  id: string;
  org_id: string;
  result_id: string;
  actor_id: string;
  feedback_type: "up" | "down";
  rating: number | null;
  category: string | null;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeedbackSubmitPayload {
  feedback_type: "up" | "down";
  rating?: number | null;
  category?: string | null;
  comment?: string | null;
}

export interface FeedbackQuery {
  page?: number;
  size?: number;
  result_id?: string;
  feedback_type?: "up" | "down";
}

export interface TrendPoint {
  bucket: string;
  value: number;
}

export interface ModelQualityMetric {
  model_key: string;
  result_count: number;
  pass_rate: number;
  hallucination_rate: number;
  thumbs_down_rate: number;
}

export interface QualityReport {
  total_results: number;
  hallucination_rate: number;
  thumbs_down_rate: number;
  avg_risk_score: number;
  feedback_distribution: Record<string, number>;
  hallucination_trend: TrendPoint[];
  thumbs_down_trend: TrendPoint[];
  model_metrics: ModelQualityMetric[];
}

export interface QualityTraceItem {
  trace_id: string;
  result_id: string | null;
  task_id: string | null;
  verdict: string | null;
  model_key: string | null;
  total_tokens: number;
  feedback_count: number;
  thumbs_down_count: number;
  last_score_value: number | null;
  last_score_at: string | null;
  created_at: string | null;
}
