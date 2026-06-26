import type { InspectionResult } from "@/types/result.types";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

export function extractResultReport(result: InspectionResult | null | undefined): string {
  const reasoning = asRecord(result?.reasoning_chain);
  const report = reasoning?.report;
  return typeof report === "string" ? report.trim() : "";
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
