import type { AgentErrorPayload, ChatMessagePayload } from "@/types/chat.types";

export function agentLabel(payload: Pick<ChatMessagePayload, "agent"> | null | undefined): string {
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
  };
}
