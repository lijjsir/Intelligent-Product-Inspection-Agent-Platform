import { describe, expect, it } from "vitest";
import { agentErrorBrief, agentErrorPayload, agentLabel } from "./chat-rendering";

describe("chat rendering helpers", () => {
  it("uses new route agent names without quality_chat fallback labels", () => {
    expect(agentLabel({ agent: "evidence" })).toBe("EvidenceArbitrationAgent");
    expect(agentLabel({ agent: "vision" })).toBe("VisionInspectionAgent");
    expect(agentLabel({ agent: "lab_detection" })).toBe("LabDetectionAgent");
    expect(agentLabel({ agent: "quality_analysis" })).toBe("QualityAnalysisAgent");
    expect(agentLabel({ agent: "memory_governance" })).toBe("MemoryGovernanceAgent");
    expect(agentLabel({ agent: "quality_chat" })).toBe("");
  });

  it("prefers the unified agent error payload over legacy string fields", () => {
    const error = agentErrorPayload({
      error_code: "LEGACY",
      error: {
        code: "CHAT_COMPOSE_MODEL_UNAVAILABLE",
        title: "回复生成模型不可用",
        message: "模型不可用，无法组织最终回复。",
        category: "model",
        severity: "error",
        status: "failed",
        frontend_visible: true,
        retryable: true,
        user_action: "请检查后台聊天模型配置。",
        trace_id: "trace-1",
        request_id: "req-1",
        stage: "quality_analysis",
        agent_name: "quality_analysis",
      },
    });

    expect(error?.code).toBe("CHAT_COMPOSE_MODEL_UNAVAILABLE");
    expect(error?.title).toBe("回复生成模型不可用");
    expect(error?.message).toBe("模型不可用，无法组织最终回复。");
    expect(error?.user_action).toBe("请检查后台聊天模型配置。");
    expect(error?.trace_id).toBe("trace-1");
    expect(error?.request_id).toBe("req-1");
    expect(error?.stage).toBe("quality_analysis");
    expect(error?.agent_name).toBe("quality_analysis");
  });

  it("normalizes legacy error fields for old messages", () => {
    const error = agentErrorPayload({
      error_code: "FILE_PARSE_FAILED",
      error: "文件解析失败",
      suggestion: "请重新上传文件。",
      trace_id: "trace-legacy",
    });

    expect(error).toMatchObject({
      code: "FILE_PARSE_FAILED",
      title: "执行失败",
      message: "文件解析失败",
      user_action: "请重新上传文件。",
      trace_id: "trace-legacy",
    });
  });

  it("keeps the visible agent error message brief and non-technical", () => {
    const brief = agentErrorBrief({
      code: "INTERNAL_AGENT_ERROR",
      title: "系统内部错误",
      message: "系统执行失败，请稍后重试。",
      category: "internal",
      severity: "error",
      status: "failed",
      frontend_visible: true,
      retryable: false,
      source: "quality.final_analyze",
      trace_id: "trace-1",
      request_id: "req-1",
      detail: { raw_error: "stack trace" },
    });

    expect(brief.title).toBe("系统内部错误");
    expect(brief.message).toBe("系统执行失败，请稍后重试。");
    expect(`${brief.title}${brief.message}`).not.toContain("INTERNAL_AGENT_ERROR");
    expect(`${brief.title}${brief.message}`).not.toContain("trace-1");
    expect(`${brief.title}${brief.message}`).not.toContain("quality.final_analyze");
  });
});
