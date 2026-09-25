import { describe, expect, it } from "vitest";
import type { InspectionResult } from "@/types/result.types";
import { extractRagSummary, extractResultCitations, isCalibratedScore } from "./result-detail-display";

function result(overrides: Partial<InspectionResult> = {}): InspectionResult {
  return {
    id: "result-1", task_id: "task-1", org_id: "org-1", verdict: "manual_required",
    overall_score: 0.95, score_status: "not_calibrated", defects: [], citations: { items: [] },
    reasoning_chain: null, llm_model: "quality", prompt_version: "quality_analysis_prompt_v1",
    tokens_used: null, latency_ms: null, reviewed_by: null, reviewed_at: null, review_note: null,
    created_at: null, ...overrides,
  };
}

describe("result trustworthiness display", () => {
  it("does not display empty wrappers as citations", () => {
    expect(extractResultCitations(result({ citations: { items: [{ title: "视觉检测结果" }] } }))).toEqual([]);
  });

  it("shows only citations with a verifiable source and quote", () => {
    const citations = extractResultCitations(result({
      citations: { items: [{ id: "chunk-1", kind: "rag", title: "标准原文", source: "标准库/a.pdf", quote: "不得氧化", score: 0.86 }] },
    }));
    expect(citations).toEqual([{ id: "chunk-1", title: "标准原文", source: "标准库/a.pdf", quote: "不得氧化", score: 0.86 }]);
  });

  it("exposes RAG execution separately from citations and hides uncalibrated scores", () => {
    const value = result({ reasoning_chain: { rag_summary: { attempted: true, hit_count: 0 } } });
    expect(extractRagSummary(value)).toMatchObject({ attempted: true, hit_count: 0 });
    expect(isCalibratedScore(value)).toBe(false);
    expect(isCalibratedScore(result({ score_status: "calibrated" }))).toBe(true);
  });
});
