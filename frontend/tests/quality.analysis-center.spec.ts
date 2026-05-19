import { describe, expect, it } from "vitest";

import { governanceRoutes } from "@/router/routes/governance.routes";

describe("quality analysis center navigation", () => {
  it("uses analysis center as the tracked merged quality entry", () => {
    const names = governanceRoutes.map((route) => route.name);
    const analysisCenter = governanceRoutes.find((route) => route.name === "governance-analysis-center");
    const report = governanceRoutes.find((route) => route.name === "governance-quality-report");
    const tracing = governanceRoutes.find((route) => route.name === "governance-quality-tracing");

    expect(names).toContain("governance-analysis-center");
    expect(analysisCenter?.path).toBe("quality/analysis-center");
    expect(analysisCenter?.meta?.title).toBe("分析中心");
    expect(report).toMatchObject({ redirect: { name: "governance-analysis-center", query: { tab: "quality" } } });
    expect(tracing).toMatchObject({ redirect: { name: "governance-analysis-center", query: { tab: "tracing" } } });
  });
});
