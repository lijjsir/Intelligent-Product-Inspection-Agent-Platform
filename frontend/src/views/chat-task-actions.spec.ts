import { describe, expect, it } from "vitest";
import { canConfirmTaskAction, hasTaskAction } from "@/views/chat-task-actions";
import type { ChatMessage } from "@/types/chat.types";

function assistantMessage(actionState: string): ChatMessage {
  return {
    id: `msg-${actionState}`,
    session_id: "session-1",
    seq_no: 1,
    role: "assistant",
    message_type: "task_action",
    content: "需要补充检测任务信息。",
    payload: {
      action_state: actionState,
    },
    created_at: "2026-05-17T09:00:00Z",
  };
}

describe("chat task actions", () => {
  it("shows a fill form action for clarification task responses", () => {
    expect(hasTaskAction(assistantMessage("awaiting_clarification"))).toBe(true);
  });

  it("only allows direct confirmation when the task draft is complete", () => {
    expect(canConfirmTaskAction(assistantMessage("awaiting_clarification"))).toBe(false);
    expect(canConfirmTaskAction(assistantMessage("awaiting_task_confirmation"))).toBe(true);
  });
});
