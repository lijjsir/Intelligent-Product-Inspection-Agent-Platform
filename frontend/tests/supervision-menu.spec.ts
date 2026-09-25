import { describe, it, expect } from "vitest";
import { appRoutes } from "@/router/routes/app.routes";
import { opsRoutes } from "@/router/routes/ops.routes";
import { cleanFields, fields } from "@/components/business/supervision/form-fields";
import { createPinia, setActivePinia } from "pinia";
import { useMenu } from "@/composables/useMenu";
import { useAuthStore } from "@/stores/auth.store";

describe("supervision role boundaries and business form submission", () => {
  it("keeps risk cases away from technical roles and exposes granted-sample intake to engineers", () => {
    const cases = appRoutes.find((r) => r.name === "app-risk-cases");
    expect(cases?.meta.roles).toContain("user");
    expect(cases?.meta.roles).toContain("expert");
    expect(cases?.meta.roles).not.toContain("algorithm_engineer");
    expect(cases?.meta.roles).not.toContain("app_developer");
    expect(opsRoutes.find((r) => r.name === "ops-data-business-samples")?.meta.roles).toEqual([
      "algorithm_engineer",
    ]);
  });
  it("exposes the streamlined quality-supervision workbench only to business roles", () => {
    const workbench = appRoutes.find((r) => r.name === "app-supervision-workbench");
    expect(workbench?.meta.roles).toEqual(["user", "expert"]);
  });
  it("keeps the v2 business chain concise and groups tasks with results", () => {
    setActivePinia(createPinia());
    const auth = useAuthStore();
    auth.role = "expert";
    auth.roles = ["expert"];
    const { menu } = useMenu();
    const quality = menu.value.find((item) => "items" in item && item.title === "质量监督");
    expect(quality && "items" in quality ? quality.items.map((item) => item.title) : []).toEqual([
      "质监工作台",
      "市场监控",
      "舆情监测",
      "监督抽查",
      "实验室检测",
    ]);
    const taskResult = menu.value.find((item) => "items" in item && item.title === "任务与结果");
    expect(
      taskResult && "items" in taskResult ? taskResult.items.map((item) => item.title) : [],
    ).toEqual(["任务管理", "检测结果"]);
  });
  it("submits only editable case inputs and retains nested real-source evidence", () => {
    const result = cleanFields(
      {
        description: "续航下降",
        occurred_at: "2026-09-16T10:00:00",
        analysis: { risk_level: "high" },
        knowledge_status: "current",
        enterprise_id: "",
        evidence: [
          {
            evidence_id: "E1",
            source_id: "C1",
            source_type: "complaint",
            occurred_at: "2026-09-16T10:00:00",
            text: "原始投诉",
            nature: "observed",
            fabricated_score: 1,
          },
        ],
      },
      fields["risk-cases"],
    );
    expect(result).not.toHaveProperty("analysis");
    expect(result).not.toHaveProperty("knowledge_status");
    expect(result).not.toHaveProperty("enterprise_id");
    expect(result.evidence[0]).toMatchObject({
      evidence_id: "E1",
      nature: "observed",
      text: "原始投诉",
    });
    expect(result.evidence[0]).not.toHaveProperty("fabricated_score");
  });
});
