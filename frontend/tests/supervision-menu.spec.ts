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
    expect(cases?.redirect).toBeUndefined();
    expect(cases?.component).toBeTypeOf("function");
    expect(cases?.meta.roles).not.toContain("user");
    expect(cases?.meta.roles).toContain("expert");
    expect(cases?.meta.roles).not.toContain("algorithm_engineer");
    expect(cases?.meta.roles).not.toContain("app_developer");
    expect(opsRoutes.find((r) => r.name === "ops-data-business-samples")?.meta.roles).toEqual([
      "algorithm_engineer",
    ]);
  });
  it("retires the workbench and redirects old links to business pages", () => {
    expect(appRoutes.find(r => r.name === "app-supervision-workbench")).toBeUndefined();
    const workbench = appRoutes.find(r => r.path === "workbench");
    expect(workbench?.component).toBeUndefined();
    expect(typeof workbench?.redirect).toBe("function");
    const redirect = workbench?.redirect as (to: { hash: string }) => string;
    expect(redirect({ hash: '' })).toBe('/app/quality-analytics');
    expect(redirect({ hash: '#demo-case-guide' })).toBe('/app/quality-data#demo-case-guide');
  });
  it("separates overview, quality analysis and independent supporting modules", () => {
    setActivePinia(createPinia());
    const auth = useAuthStore();
    auth.role = "expert";
    auth.roles = ["expert"];
    const { menu } = useMenu();
    const quality = menu.value.find((item) => "items" in item && item.title === "质量监督");
    expect(quality && "items" in quality ? quality.items.map((item) => item.title) : []).toEqual([
      "数据采集",
      "市场监控",
      "风险研判",
      "监督抽查",
      "实验室检测",
    ]);
    expect(menu.value.map(item => item.title)).toEqual(["AI 对话", "会议室", "质量监督", "检测任务", "检测结果", "报告中心", "标准审核", "知识资料", "个人设置"]);
    for (const title of ['检测任务','检测结果','会议室','报告中心','标准审核','知识资料']) {
      expect(menu.value.some(item => item.title === title && !('items' in item))).toBe(true);
    }
    expect(menu.value.some(item => item.title === '标准与知识')).toBe(false);
    const paths = menu.value.flatMap(item => 'items' in item ? item.items.map(child => child.path) : [item.path]);
    expect(new Set(paths).size).toBe(paths.length);
  });
  it("keeps historical risk evidence editable within risk assessment", () => {
    const record = appRoutes.find(r => r.name === 'app-supervision-risk-records');
    expect(record?.path).toBe('risk-assessments/records/risk-cases');
    expect(record?.meta.supervisionKind).toBe('risk-cases');
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
