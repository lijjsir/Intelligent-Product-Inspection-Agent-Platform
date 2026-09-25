import type { SupervisionKind } from "@/types/supervision.types";
export interface FieldSpec {
  key: string;
  label: string;
  type?: string;
  options?: string;
  required?: boolean;
  multiple?: boolean;
  dependsOn?: string;
  fields?: FieldSpec[];
}
export interface FieldOption {
  value: string;
  label: string;
  product_sku_id?: string;
}
export function fieldOptions(
  field: FieldSpec,
  model: Record<string, any>,
  options: Record<string, FieldOption[]>,
): FieldOption[] {
  const available = options[field.options || ""] || [];
  if (!field.dependsOn) return available;
  const dependencyValue = model[field.dependsOn];
  if (!dependencyValue) return [];
  return available.filter((option) => option.product_sku_id === dependencyValue);
}
export function clearInvalidDependencies(
  model: Record<string, any>,
  changedKey: string,
  specs: FieldSpec[],
  options: Record<string, FieldOption[]>,
): Record<string, any> {
  const next = { ...model };
  for (const field of specs) {
    if (field.dependsOn !== changedKey || !next[field.key]) continue;
    if (!fieldOptions(field, next, options).some((option) => option.value === next[field.key]))
      next[field.key] = undefined;
  }
  return next;
}
const ref = (
  key: string,
  label: string,
  options: string,
  required = false,
  multiple = false,
  dependsOn?: string,
): FieldSpec => ({ key, label, type: "select", options, required, multiple, dependsOn });
export const testFields: FieldSpec[] = [
  { key: "item", label: "检测项目", required: true },
  { key: "unit", label: "单位", required: true },
  { key: "method", label: "检测方法", required: true },
  { key: "lower_limit", label: "标准下限", type: "number" },
  { key: "upper_limit", label: "标准上限", type: "number" },
  { key: "standard_ref", label: "标准与条款依据" },
  { key: "normal_lower", label: "正常响应下限", type: "number" },
  { key: "normal_upper", label: "正常响应上限", type: "number" },
];
export const fields: Record<SupervisionKind, FieldSpec[]> = {
  regions: [
    ref("parent_id", "上级地区", "regions"),
    { key: "dictionary_version", label: "字典版本", required: true },
  ],
  enterprises: [
    { key: "credit_code", label: "社会信用代码" },
    ref("role", "企业角色", "enterpriseRoles", true),
    { key: "address", label: "地址" },
    ref("region_id", "所在地区", "regions"),
    ref("product_sku_ids", "关联产品", "products", false, true),
  ],
  devices: [
    { key: "device_type", label: "设备类型", required: true },
    ref("region_id", "所在地区", "regions"),
    { key: "location", label: "具体位置" },
    { key: "capabilities", label: "检测能力（逗号分隔）", type: "strings" },
    ref("calibration_status", "校准状态", "calibration", true),
    { key: "calibration_expires_at", label: "校准有效期", type: "date" },
    ref("online_status", "运行状态", "online", true),
    { key: "capacity", label: "可用样本容量", type: "number", required: true },
    { key: "connection_description", label: "连接说明" },
    { key: "baseline_version", label: "基线版本" },
  ],
  "risk-cases": [
    ref("product_sku_id", "产品", "products"),
    ref("batch_id", "批次", "batches", false, false, "product_sku_id"),
    ref("enterprise_id", "被监管企业", "enterprises"),
    { key: "product_category", label: "产品类别" },
    ref("production_region_id", "生产地", "regions"),
    ref("sales_region_ids", "销售地", "regions", false, true),
    ref("complaint_region_id", "投诉发生地", "regions"),
    ref("sampling_region_id", "抽样地", "regions"),
    ref("inspection_standard_id", "适用检测标准", "standards"),
    { key: "occurred_at", label: "线索发生时间", type: "date", required: true },
    { key: "description", label: "问题描述", type: "textarea", required: true },
    ref("assigned_to", "负责人", "assignees"),
    {
      key: "evidence",
      label: "来源证据",
      type: "array",
      fields: [
        { key: "evidence_id", label: "证据编号", required: true },
        ref("source_type", "来源类型", "sources", true),
        { key: "source_id", label: "来源记录编号", required: true },
        { key: "occurred_at", label: "发生时间", type: "date", required: true },
        { key: "text", label: "证据内容", type: "textarea", required: true },
        { key: "attachment_url", label: "原始附件地址" },
        ref("nature", "证据性质", "natures", true),
      ],
    },
  ],
  "market-monitoring-reports": [
    { key: "window_start", label: "监控开始时间", type: "date", required: true },
    { key: "window_end", label: "监控结束时间", type: "date", required: true },
    { key: "exposure_ids", label: "统计基数记录", type: "strings" },
    { key: "denominator_kind", label: "统计分母类型" },
    { key: "dimensions", label: "分析维度", type: "strings" },
  ],
  "public-opinion-reports": [
    ref("risk_case_id", "关联舆情案件", "cases", true),
    { key: "evidence_ids", label: "证据编号", type: "strings" },
    { key: "source_types", label: "来源类型", type: "strings" },
    { key: "standard_snapshot_id", label: "标准快照" },
    { key: "knowledge_snapshot_id", label: "知识快照" },
  ],
  "risk-assessments": [
    { key: "market_report_id", label: "市场监控报告" },
    { key: "public_opinion_report_id", label: "舆情监测报告" },
    { key: "risk_level", label: "风险等级" },
    { key: "evidence_ids", label: "证据编号", type: "strings" },
    { key: "standard_snapshot_id", label: "标准快照" },
    { key: "knowledge_snapshot_id", label: "知识快照" },
    { key: "missing_inputs", label: "缺失输入", type: "strings" },
    { key: "conflicts", label: "待处理冲突", type: "strings" },
  ],
  "sampling-plans": [
    { key: "budget", label: "预算", type: "number", required: true },
    { key: "max_samples", label: "最多样本数", type: "number", required: true },
    { key: "max_staff_hours", label: "可用人员工时", type: "number", required: true },
    { key: "hours_per_sample", label: "每样本工时", type: "number", required: true },
    { key: "required_categories", label: "必须覆盖类别（逗号分隔）", type: "strings" },
    { key: "starts_at", label: "计划开始", type: "date" },
    { key: "ends_at", label: "计划结束", type: "date" },
    {
      key: "candidates",
      label: "候选对象",
      type: "array",
      fields: [
        ref("case_id", "已确认风险案件", "cases", true),
        { key: "sample_count", label: "抽样数量", type: "number", required: true },
        { key: "unit_cost", label: "每样本成本", type: "number", required: true },
        ref("device_id", "检测设备", "devices"),
        ref("region_id", "抽样地", "regions"),
        { key: "required_items", label: "必检项目", type: "array", fields: testFields },
        { key: "candidate_items", label: "动态候选项目", type: "array", fields: testFields },
      ],
    },
  ],
  samples: [
    ref("task_id", "检测任务", "tasks", true),
    ref("product_sku_id", "产品", "products", true),
    ref("batch_id", "批次", "batches", true, false, "product_sku_id"),
    { key: "sampled_at", label: "抽样时间", type: "date", required: true },
    ref("sampling_region_id", "抽样地", "regions"),
  ],
  "inspection-sessions": [
    ref("task_id", "检测任务", "tasks", true),
    ref("case_id", "关联风险案件", "cases"),
    ref("plan_id", "已批准抽查计划", "plans"),
    ref("sample_ids", "样品", "samples", true, true),
    ref("device_ids", "设备", "devices", true, true),
    { key: "baseline_version", label: "正常响应基线版本" },
    { key: "required_items", label: "必检项目", type: "array", fields: testFields },
    { key: "candidate_items", label: "动态候选项目", type: "array", fields: testFields },
    { key: "adaptive_enabled", label: "启用设备闭环", type: "boolean" },
  ],
  exposures: [
    ref("region_id", "统计地区", "regions", true),
    { key: "product_category", label: "产品类别", required: true },
    { key: "period_start", label: "统计开始", type: "date", required: true },
    { key: "period_end", label: "统计结束", type: "date", required: true },
    { key: "sales_volume", label: "销量", type: "number" },
    { key: "in_use_volume", label: "在用量", type: "number" },
    { key: "inspection_count", label: "实际抽查数", type: "number" },
    { key: "source_id", label: "数据来源", required: true },
  ],
  baselines: [
    ref("device_ids", "适用设备", "devices", false, true),
    { key: "product_category", label: "产品类别", required: true },
    { key: "version_label", label: "版本", required: true },
    { key: "source_id", label: "真实数据来源", required: true },
    { key: "conditions", label: "适用工况", type: "textarea", required: true },
    { key: "test_items", label: "正常响应范围", type: "array", fields: testFields },
  ],
};
export const defaults: Record<SupervisionKind, Record<string, any>> = {
  regions: { dictionary_version: "2026" },
  enterprises: { role: "manufacturer", product_sku_ids: [] },
  devices: {
    device_type: "",
    capabilities: [],
    capacity: 1,
    calibration_status: "unknown",
    online_status: "unknown",
  },
  "risk-cases": {
    occurred_at: new Date().toISOString(),
    description: "",
    sales_region_ids: [],
    evidence: [],
    product_category: "电动自行车",
  },
  "market-monitoring-reports": {
    window_start: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    window_end: new Date().toISOString(),
    case_versions: {},
    exposure_ids: [],
    dimensions: ["region", "enterprise", "product_category"],
  },
  "public-opinion-reports": { evidence_ids: [], source_types: [] },
  "risk-assessments": {
    risk_level: "unknown",
    evidence_ids: [],
    missing_inputs: [],
    conflicts: [],
  },
  "sampling-plans": {
    budget: 0,
    max_samples: 10,
    max_staff_hours: 8,
    hours_per_sample: 1,
    required_categories: [],
    candidates: [],
  },
  samples: { sampled_at: new Date().toISOString() },
  "inspection-sessions": {
    sample_ids: [],
    device_ids: [],
    test_items: [],
    required_items: [],
    candidate_items: [],
    adaptive_enabled: false,
  },
  exposures: {},
  baselines: { device_ids: [], test_items: [] },
};
export function cleanFields(data: Record<string, any>, specs: FieldSpec[]): Record<string, any> {
  const out: Record<string, any> = {};
  for (const f of specs) {
    const value = data[f.key];
    if (f.type === "array")
      out[f.key] = (value || []).map((item: any) => cleanFields(item, f.fields || []));
    else if (value !== "" && value !== undefined && value !== null) out[f.key] = value;
    else if (f.required) out[f.key] = value;
  }
  return out;
}
