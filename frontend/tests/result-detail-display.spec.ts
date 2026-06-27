import { describe, expect, it } from "vitest";

import {
  buildDefectEmptyDescription,
  buildDefectImageNotice,
  extractResultReport,
  extractVisualPossibleDefects,
  extractStandardEvaluation,
  shouldShowDefectImagePanel,
} from "@/views/result-detail-display";
import type { InspectionResult } from "@/types/result.types";

function resultFixture(overrides: Partial<InspectionResult> = {}): InspectionResult {
  return {
    id: "result-1",
    task_id: "task-1",
    org_id: "org-1",
    verdict: "manual_required",
    overall_score: 0.85,
    defects: [],
    citations: { items: [] },
    reasoning_chain: null,
    llm_model: "deepseek-v4-flash",
    prompt_version: "quality_analysis_prompt_v1",
    tokens_used: 775,
    latency_ms: 85769,
    reviewed_by: null,
    reviewed_at: null,
    review_note: null,
    created_at: null,
    ...overrides,
  };
}

describe("result detail display helpers", () => {
  it("surfaces the persisted quality report even when no bbox defects were generated", () => {
    const result = resultFixture({
      reasoning_chain: {
        report: "# 正式质检报告\n\n尺寸、硬度、扭矩均符合检测标准。",
        standard_evaluation: { gate: "llm_only", passed: true },
      },
    });

    expect(extractResultReport(result)).toContain("正式质检报告");
    expect(extractStandardEvaluation(result)).toEqual({ gate: "llm_only", passed: true });
    expect(buildDefectEmptyDescription(result)).toBe("未生成视觉缺陷坐标，质量分析报告已在上方展示。");
  });

  it("replaces mojibake or English report templates with a Chinese fallback", () => {
    const result = resultFixture({
      verdict: "manual_required",
      overall_score: 0.94,
      reasoning_chain: {
        report: "# 姝ｅ紡璐ㄦ鎶ュ憡\n\n**Quality Inspection Report**\nInspection Status: Manual Required",
        standard_evaluation: {
          gate: "inspection_standard",
          passed: false,
          summary: "按标准 AUTO-HAZELNUT-V1 校验未达到自动放行条件。",
          reasons: ["low_evidence"],
        },
        visual_inspection_result: {
          summary: "榛子外观完整，未返回明确缺陷坐标。",
        },
      },
    });

    const report = extractResultReport(result);

    expect(report).toContain("# 正式质检报告");
    expect(report).toContain("按标准 AUTO-HAZELNUT-V1 校验未达到自动放行条件。");
    expect(report).toContain("榛子外观完整");
    expect(report).not.toContain("姝ｅ紡");
    expect(report).not.toContain("Quality Inspection Report");
  });

  it("keeps the plain empty-defect message when no analysis detail exists", () => {
    expect(buildDefectEmptyDescription(resultFixture())).toBe("未检出明确缺陷");
  });

  it("keeps the defect image panel visible when task images exist without bbox defects", () => {
    const result = resultFixture({
      reasoning_chain: {
        visual_inspection_result: {
          possible_defects: ["苹果表面疑似腐烂", "局部颜色异常"],
        },
      },
    });

    expect(shouldShowDefectImagePanel(["/uploads/apple.jpg"], result)).toBe(true);
    expect(extractVisualPossibleDefects(result)).toEqual(["苹果表面疑似腐烂", "局部颜色异常"]);
    expect(buildDefectImageNotice(result)).toBe("模型返回了可能缺陷描述，但没有返回真实 bbox 坐标；当前仅展示原图，不标注推测位置。");
  });

  it("hides the defect image panel when no task image is available", () => {
    expect(shouldShowDefectImagePanel([], resultFixture())).toBe(false);
  });
});
