export type SupervisionKind =
  | "enterprises"
  | "regions"
  | "devices"
  | "risk-cases"
  | "market-monitoring-reports"
  | "public-opinion-reports"
  | "risk-assessments"
  | "sampling-plans"
  | "inspection-sessions"
  | "samples"
  | "exposures"
  | "baselines";
export interface SupervisionRecord {
  id: string;
  org_id: string;
  kind: SupervisionKind;
  code: string;
  name: string;
  status: string;
  version: number;
  created_by: string;
  assigned_to?: string;
  data: Record<string, any>;
  created_at: string;
  updated_at: string;
}
export interface SupervisionRun {
  id: string;
  record_id: string;
  input_version: number;
  agent: string;
  status: string;
  iteration: number;
  output?: Record<string, any>;
  error?: string;
}
export interface BusinessTodo {
  id: string;
  record_id: string;
  kind: SupervisionKind;
  name: string;
  operation: string;
  version: number;
}
export const KIND_LABELS: Record<SupervisionKind, string> = {
  enterprises: "监管对象",
  regions: "地区字典",
  devices: "设备管理",
  "risk-cases": "舆情监测",
  "market-monitoring-reports": "市场监控报告",
  "public-opinion-reports": "舆情监测报告",
  "risk-assessments": "风险评估",
  "sampling-plans": "监督抽查",
  "inspection-sessions": "检测会话",
  samples: "样品登记",
  exposures: "态势基础数据",
  baselines: "正常响应基线",
};
export const STATUS_LABELS: Record<string, string> = {
  planned: "待实际抽样",
  active: "启用",
  inactive: "停用",
  archived: "归档",
  draft: "草稿",
  collecting: "采集中",
  queued: "已排队",
  running: "分析中",
  awaiting_evidence: "待补证",
  awaiting_review: "待复核",
  awaiting_device: "等待设备",
  awaiting_retest: "等待复测",
  risk_assessed: "风险已确认",
  approved: "已批准",
  signed: "已签发",
  completed: "分析完成",
  failed: "失败",
  manual_review_required: "需人工复核",
  insufficient_evidence: "证据不足",
  infeasible: "方案不可行",
  stale: "版本已变化",
  cancelled: "已取消",
  unknown: "未知",
  accepted: "通过",
  goal_reached: "检测目标已达成",
  pending: "待处理",
};
export const OP_LABELS: Record<string, string> = {
  "risk.review": "舆情风险复核",
  "sampling.approve": "抽查方案确认",
  "result.review": "结果复核",
  "result.signoff": "正式结果确认",
  request_evidence: "补充证据",
};

export interface InspectionTestItem {
  item: string;
  unit: string;
  method: string;
  lower_limit?: number | null;
  upper_limit?: number | null;
  standard_ref?: string | null;
  normal_lower?: number | null;
  normal_upper?: number | null;
}

export interface InspectionGoal {
  id: string;
  org_id: string;
  session_id: string;
  plan_id?: string | null;
  version: number;
  request_key: string;
  status: string;
  risk_hypotheses: string[];
  required_items: InspectionTestItem[];
  candidate_items: InspectionTestItem[];
  success_criteria: Record<string, unknown>;
  stop_policy: Record<string, unknown>;
  max_cost?: number | null;
  max_duration_seconds?: number | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface DeviceTrustState {
  status: "trusted" | "suspect" | "invalid" | "unknown";
  device_ids: string[];
  calibration_valid: boolean;
  quality_issues: string[];
}

export interface ProductQualityState {
  status: "normal" | "abnormal" | "uncertain";
  supported_hypotheses: string[];
  rejected_hypotheses: string[];
  findings: Array<Record<string, unknown>>;
}

export interface InspectionEvidenceState {
  id: string;
  session_id: string;
  round: number;
  device_trust_state: DeviceTrustState;
  product_quality_state: ProductQualityState;
  supported_hypotheses: string[];
  rejected_hypotheses: string[];
  unresolved_conflicts: string[];
  evidence_sufficiency: number;
  remaining_uncertainty: number;
  evidence_ids: string[];
  created_at: string;
}

export interface InspectionDecision {
  id: string;
  session_id: string;
  round: number;
  kind:
    | "next_test"
    | "goal_reached"
    | "full_plan_required"
    | "retest_required"
    | "device_change_required"
    | "manual_review_required"
    | "blocked";
  status: string;
  input_state_id: string;
  request_key: string;
  payload: Record<string, unknown>;
  rule_version: string;
  proposed_by: string;
  approved_by?: string | null;
  created_at: string;
  reviewed_at?: string | null;
}
