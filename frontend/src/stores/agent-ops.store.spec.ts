import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { agentOpsApi } from "@/api/agent-ops.api";
import { useAgentOpsStore } from "@/stores/agent-ops.store";

vi.mock("@/api/agent-ops.api", () => ({
  agentOpsApi: {
    getRagAnalysis: vi.fn(),
    getRagTraceDetail: vi.fn(),
  },
}));

describe("agent ops store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(agentOpsApi.getRagAnalysis).mockReset();
    vi.mocked(agentOpsApi.getRagTraceDetail).mockReset();
  });

  it("stores rag trace detail with evidence chain fields", async () => {
    vi.mocked(agentOpsApi.getRagTraceDetail).mockResolvedValue({
      data: {
        data: {
          trace_id: "trace-1",
          query: "苹果表面划痕如何判断",
          rag_space_id: "space-1",
          rag_space_name: "质量知识库",
          source_agent: "Inspection Task Agent",
          source_graph: "inspection_task",
          sub_route: "inspection_execute",
          top_k: 6,
          hit_count: 3,
          hit_rate: 0.5,
          citation_coverage: 1,
          latency_ms: 420,
          evidence_found: true,
          evidence_used: true,
          verdict_impacted: true,
          retrieval_config: { top_k: 6 },
          retrieved_chunks: [{ chunk_id: "c1", score: 0.87 }],
          used_citations: [{ chunk_id: "c1", quote: "划痕宽度超过阈值" }],
          rule_hits: ["scratch_rule"],
          verdict: "reject",
          answer: "依据知识库建议判为不合格。",
          result: { score: "reject" },
          top_sources: ["苹果质检标准"],
          created_at: "2026-05-20T10:00:00Z",
        },
      },
    } as any);

    const store = useAgentOpsStore();
    const detail = await store.fetchRagTraceDetail("trace-1");

    expect(agentOpsApi.getRagTraceDetail).toHaveBeenCalledWith("trace-1");
    expect(detail.source_graph).toBe("inspection_task");
    expect(detail.source_agent).toBe("Inspection Task Agent");
    expect(detail.evidence_found).toBe(true);
    expect(detail.evidence_used).toBe(true);
    expect(detail.verdict_impacted).toBe(true);
    expect(store.ragTraceDetail?.top_sources).toEqual(["苹果质检标准"]);
  });
});
