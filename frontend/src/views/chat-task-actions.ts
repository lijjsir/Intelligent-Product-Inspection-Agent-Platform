import type { ChatMessage } from "@/types/chat.types";

const ACTIONABLE_TASK_STATES = new Set([
  "awaiting_clarification",
  "awaiting_task_details",
  "awaiting_task_confirmation",
]);

export function hasTaskAction(message: ChatMessage) {
  const state = message.payload?.action_state;
  return ACTIONABLE_TASK_STATES.has(String(state || ""));
}

export function canConfirmTaskAction(message: ChatMessage) {
  return message.payload?.action_state === "awaiting_task_confirmation";
}
