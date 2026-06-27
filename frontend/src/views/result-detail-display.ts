import type { InspectionResult } from "@/types/result.types";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function hasMojibake(text: string): boolean {
  return /[姝璐佹嵁紡憡]|�/.test(text);
}

function hasEnglishReportTemplate(text: string): boolean {
  return /Quality Inspection Report|Inspection Status|Insufficient Evidence|Manual Required/i.test(text);
}

function verdictLabel(value: unknown): string {
  const verdict = String(value || "").toLowerCase();
  const labels: Record<string, string> = {
    pass: "产品合格",
    fail: "产品不合格",
    uncertain: "暂未判定",
    manual_required: "需人工复核",
  };
  return labels[verdict] || String(value || "暂未判定");
}

function buildChineseReportFallback(result: InspectionResult | null | undefined): string {
  const reasoning = asRecord(result?.reasoning_chain);
  const standard = asRecord(reasoning?.standard_evaluation);
  const visual = asRecord(reasoning?.visual_inspection_result);
  if (!standard && !visual) return "";

  const lines = [
    "# 正式质检报告",
    "",
    "## 检测结论",
    standard?.summary ? String(standard.summary) : `当前系统判定：${verdictLabel(result?.verdict)}。`,
    "",
    "## 证据依据",
    `综合置信分：${(((result?.overall_score ?? 0) as number) * 100).toFixed(1)} 分。`,
  ];

  if (Array.isArray(standard?.reasons) && standard.reasons.length > 0) {
    lines.push(`规则原因：${standard.reasons.map(String).join("；")}。`);
  }
  if (Array.isArray(result?.defects) && result.defects.length > 0) {
    lines.push(`检出缺陷：${result.defects.length} 个。`);
  }

  lines.push("", "## 图像观察");
  lines.push(visual?.summary ? String(visual.summary) : "当前结果未提供可读的图像观察摘要。");

  lines.push("", "## 标准校验");
  if (standard) {
    lines.push(`校验门禁：${String(standard.gate || "-")}。`);
    if (typeof standard.passed === "boolean") {
      lines.push(`是否通过：${standard.passed ? "是" : "否"}。`);
    }
  } else {
    lines.push("当前结果未提供标准校验明细。");
  }

  lines.push("", "## 局限与建议");
  if (result?.verdict === "manual_required") {
    lines.push("自动判定未达到直接放行条件，请由人工质检人员结合原图、规则命中和证据链给出最终产品判定。");
  } else {
    lines.push("请结合原图、缺陷列表、规则命中和引用证据复查关键结论。");
  }

  return lines.join("\n");
}

export function extractResultReport(result: InspectionResult | null | undefined): string {
  const reasoning = asRecord(result?.reasoning_chain);
  const report = reasoning?.report;
  const text = typeof report === "string" ? report.trim() : "";
  if (text && !hasMojibake(text) && !hasEnglishReportTemplate(text)) return text;
  return buildChineseReportFallback(result);
}

export function extractStandardEvaluation(result: InspectionResult | null | undefined): Record<string, unknown> | null {
  const reasoning = asRecord(result?.reasoning_chain);
  return asRecord(reasoning?.standard_evaluation);
}

export function extractVisualInspectionResult(result: InspectionResult | null | undefined): Record<string, unknown> | null {
  const reasoning = asRecord(result?.reasoning_chain);
  return asRecord(reasoning?.visual_inspection_result);
}

function stringifyPossibleDefect(value: unknown): string {
  if (typeof value === "string") return value.trim();
  const record = asRecord(value);
  if (!record) return "";
  for (const key of ["description", "message", "title", "type", "label"]) {
    const candidate = record[key];
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }
  return "";
}

export function extractVisualPossibleDefects(result: InspectionResult | null | undefined): string[] {
  const visual = extractVisualInspectionResult(result);
  const modelResult = asRecord(visual?.model_result);
  const values = Array.isArray(visual?.possible_defects)
    ? visual?.possible_defects
    : Array.isArray(modelResult?.possible_defects)
      ? modelResult?.possible_defects
      : [];
  return values.map(stringifyPossibleDefect).filter(Boolean);
}

export function shouldShowDefectImagePanel(
  imageUrls: Array<string | null | undefined>,
  _result: InspectionResult | null | undefined,
): boolean {
  return imageUrls.some((item) => String(item || "").trim());
}

export function buildDefectImageNotice(result: InspectionResult | null | undefined): string {
  const defects = Array.isArray(result?.defects) ? result.defects : [];
  if (defects.length > 0) return "";
  if (extractVisualPossibleDefects(result).length > 0) {
    return "模型返回了可能缺陷描述，但没有返回真实 bbox 坐标；当前仅展示原图，不标注推测位置。";
  }
  return "当前结果没有返回视觉缺陷 bbox 坐标；当前仅展示原图。";
}

export function buildDefectEmptyDescription(result: InspectionResult | null | undefined): string {
  if (extractResultReport(result) || extractStandardEvaluation(result)) {
    return "未生成视觉缺陷坐标，质量分析报告已在上方展示。";
  }
  return "未检出明确缺陷";
}
