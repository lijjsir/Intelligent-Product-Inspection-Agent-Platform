export interface StabilityReport {
  id: string;
  task_id: string;
  result_id: string;
  org_id: string;
  evidence_score: number;
  consistency_score: number;
  confidence_score: number;
  traceability_score: number;
  anomaly_score: number;
  risk_score: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  dimension_detail: Record<string, any> | null;
  sampling_results: Record<string, any> | null;
  root_cause: string | null;
  handled_by: string | null;
  handled_at: string | null;
  handle_action: string | null;
  handle_note: string | null;
  created_at: string | null;
}
