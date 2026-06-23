import type { AgentErrorPayload, ChatMessagePayload } from "@/types/chat.types";

export function agentLabel(payload: Pick<ChatMessagePayload, "agent"> | null | undefined): string {
  if (payload?.agent === "evidence") return "EvidenceArbitrationAgent";
  if (payload?.agent === "vision") return "VisionInspectionAgent";
  if (payload?.agent === "lab_detection") return "LabDetectionAgent";
  if (payload?.agent === "quality_analysis") return "QualityAnalysisAgent";
  if (payload?.agent === "memory_governance") return "MemoryGovernanceAgent";
  if (payload?.agent === "chat") return "ChatAgent";
  if (payload?.agent === "inspection_task") return "InspectionTaskAgent";
  if (payload?.agent === "file") return "FileAgent";
  return "";
}

function isAgentErrorPayload(value: unknown): value is AgentErrorPayload {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<AgentErrorPayload>;
  return typeof candidate.code === "string" && typeof candidate.message === "string";
}

export type ChatCardType = "evidence" | "vision" | "lab" | "quality" | "trace" | "error" | "result" | "paper_review" | "task" | "text";

export function messageCardType(payload: ChatMessagePayload | null | undefined): ChatCardType {
  if (!payload) return "text";
  if (payload.quality_final_assessment) return "quality";
  if (payload.visual_inspection_result) return "vision";
  if (payload.lab_detection_result) return "lab";
  if (payload.evidence_packet) return "evidence";
  if (payload.route_trace || payload.capabilities_used?.length) return "trace";
  if (payload.error || payload.error_code) return "error";
  if (payload.result_card) return "result";
  if (payload.paper_format_report) return "paper_review";
  if (payload.created_task) return "task";
  return "text";
}

export function agentErrorPayload(payload: ChatMessagePayload | null | undefined): AgentErrorPayload | null {
  if (!payload) return null;
  if (isAgentErrorPayload(payload.error)) return payload.error;
  const legacyError = typeof payload.error === "string" ? payload.error : "";
  const code = payload.error_code || (legacyError ? "AGENT_FAILED" : "");
  if (!code && !legacyError) return null;
  return {
    code: code || "AGENT_FAILED",
    title: "执行失败",
    message: legacyError || "Agent 执行失败。",
    category: "internal",
    severity: "error",
    status: payload.status === "blocked" ? "blocked" : "failed",
    frontend_visible: true,
    retryable: false,
    user_action: payload.suggestion || null,
    source: payload.module || null,
    detail: payload.detail || null,
    workflow_run_id: payload.workflow_run_id || null,
    trace_id: payload.trace_id || null,
    stage: null,
    agent_name: payload.agent || null,
  };
}
