import type { ChatMessagePayload } from "@/types/chat.types";

export function agentLabel(payload: Pick<ChatMessagePayload, "agent"> | null | undefined): string {
  if (payload?.agent === "chat") return "QualityChatAgent";
  if (payload?.agent === "inspection_task") return "InspectionTaskAgent";
  return "";
}
